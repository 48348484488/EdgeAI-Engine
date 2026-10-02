"""Frozen, explicitly synthetic instruction tasks. No model/API-generated labels.

Group splits are by underlying string, unordered addend pair, or coefficient,
not by the rendered prompt. All templates and extrapolation ranges are explicit.
This is a diagnostic curriculum, not a general instruction or human benchmark.
"""
import argparse
import ast
import hashlib
import itertools
import json
from pathlib import Path

SPLITS=('train','valid','test_id','test_template','test_range','test_family')
TEMPLATES={
 'copy':(('Copy exactly: {s}','Copie exatamente: {s}'),('Repeat unchanged: {s}','Repita sem alterar: {s}')),
 'uppercase':(('Uppercase: {s}','Maiusculas: {s}'),('Convert to capital letters: {s}','Converta para maiusculas: {s}')),
 'addition':(('Add: {a} + {b}','Some: {a} + {b}'),('What is the sum of {a} and {b}?','Quanto vale a soma de {a} e {b}?')),
 'expression':(('Expression for x {op} {k}:','Expressao para x {op} {k}:'),('Return only the Python expression x {op} {k}.','Retorne apenas a expressao Python x {op} {k}.')),
}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def dumps(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def role(group):
    n=int(sha(('edge-v07-split-1:'+group).encode())[:8],16)%100
    return 'train' if n<70 else 'valid' if n<80 else 'test_id' if n<88 else 'test_template' if n<96 else 'test_family'

def build_dataset():
    result={s:[] for s in SPLITS}
    def add(task,group,values,answer,force=None):
        split=force or role(group)
        if split=='test_family':return
        templates=TEMPLATES[task][1 if split=='test_template' else 0]
        for lang,template in zip(('en','pt'),templates):
            row=dict(task=task,group=group,prompt=template.format(**values),answer=answer,
                     language=lang,template=f'{task}_{lang}_{"new" if split=="test_template" else "base"}')
            row['id']=sha(dumps(row).encode())[:20];result[split].append(row)
    for length in range(1,5):
        for chars in itertools.product('abcdef',repeat=length):
            s=''.join(chars);group='string:'+s
            add('copy',group,dict(s=s),s);add('uppercase',group,dict(s=s),s.upper())
            if role(group)=='test_family':
                for lang,prompt in (('en','Reverse: '+s),('pt','Inverta: '+s)):
                    row=dict(task='reverse',group=group,prompt=prompt,answer=s[::-1],language=lang,template='reverse_'+lang)
                    row['id']=sha(dumps(row).encode())[:20];result['test_family'].append(row)
    for a in range(20):
        for b in range(20):add('addition',f'pair:{min(a,b)}:{max(a,b)}',dict(a=a,b=b),str(a+b))
    for k in range(30):
        for op in ('+','-','*'):add('expression',f'coefficient:{k}',dict(op=op,k=k),f'x{op}{k}')
    # Range extrapolation: longer strings or coefficients/addends never in train.
    for chars in itertools.islice(itertools.product('abcdef',repeat=6),150):
        s=''.join(chars)
        add('copy','longstring:'+s,dict(s=s),s,'test_range')
        add('uppercase','longstring:'+s,dict(s=s),s.upper(),'test_range')
    for a in range(30,40):
        for b in range(30,40):add('addition',f'pair:{min(a,b)}:{max(a,b)}',dict(a=a,b=b),str(a+b),'test_range')
    for k in range(40,60):
        for op in ('+','-','*'):add('expression',f'coefficient:{k}',dict(op=op,k=k),f'x{op}{k}','test_range')
    # Balanced deterministic diagnostic sizes; never move rows between splits.
    for split in SPLITS:
        rows=sorted(result[split],key=lambda r:sha(('order:'+r['id']).encode()))
        if split!='train':
            limit=16 if split=='valid' else 8
            selected=[]
            for task in sorted({r['task'] for r in rows}):
                for language in ('en','pt'):
                    selected.extend([r for r in rows if r['task']==task and r['language']==language][:limit])
            rows=selected
        result[split]=rows
    validate_dataset(result)
    return result

def validate_dataset(data):
    if set(data)!=set(SPLITS):raise ValueError('missing or unknown split')
    seen_groups={};seen_prompts=set();seen_ids=set()
    for split,rows in data.items():
        if not rows:raise ValueError('empty split: '+split)
        for r in rows:
            if any(not isinstance(r.get(k),str) or not r[k] for k in ('id','group','prompt','answer','task','template','language')):
                raise ValueError('invalid instruction row')
            if r['id'] in seen_ids or r['prompt'] in seen_prompts:raise ValueError('duplicate row or prompt')
            seen_ids.add(r['id']);seen_prompts.add(r['prompt'])
            if r['group'] in seen_groups and seen_groups[r['group']]!=split:raise ValueError('cross-split input group')
            seen_groups[r['group']]=split
            if len(r['prompt'].encode())>512 or len(r['answer'].encode())>128:raise ValueError('oversized example')
    train_templates={r['template'] for r in data['train']}
    if train_templates & {r['template'] for r in data['test_template']}:raise ValueError('template overlap')
    if {r['task'] for r in data['train']} & {r['task'] for r in data['test_family']}:raise ValueError('heldout family overlap')
    return True

def write_dataset(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);data=build_dataset();files={}
    for split,rows in data.items():
        raw=('\n'.join(dumps(r) for r in rows)+'\n').encode();p=root/(split+'.jsonl');p.write_bytes(raw)
        files[p.name]=dict(sha256=sha(raw),rows=len(rows),bytes=len(raw))
    manifest=dict(format='edge-sft-synthetic-1',synthetic=True,source='deterministic local rules; no external LLM or user data',
                  license='CC0-1.0',generator_sha256=sha(Path(__file__).read_bytes()),files=files,
                  limitations=['few templates and task families; not a standardized benchmark','test_family holds out reversal; not a claim of general intelligence','base checkpoints previously pretrained on CPython, not on these prompts','labels may repeat across splits; input groups and exact prompts do not'])
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (root/'NOTICE.md').write_text('# Synthetic v0.7 curriculum\n\nGenerated by local deterministic code, not collected from people or an API.\nNew examples dedicated under CC0-1.0. Existing pretrained CPython data retains its original license.\nSee manifest.json for provenance and hashes. No frontier-model teacher is used.\n')
    return manifest

def load_dataset(root):
    root=Path(root);m=json.loads((root/'manifest.json').read_text())
    if m.get('format')!='edge-sft-synthetic-1':raise ValueError('unknown dataset format')
    data={}
    for split in SPLITS:
        raw=(root/(split+'.jsonl')).read_bytes();record=m['files'][split+'.jsonl']
        if sha(raw)!=record['sha256']:raise ValueError('dataset hash mismatch: '+split)
        data[split]=[json.loads(line) for line in raw.splitlines()]
        if len(data[split])!=record['rows']:raise ValueError('dataset row mismatch')
    validate_dataset(data);return data,m

def expression(text,x):
    if len(text)>64:raise ValueError('expression too long')
    node=ast.parse(text,mode='eval')
    def walk(n,depth=0):
        if depth>5:raise ValueError('expression too deep')
        if isinstance(n,ast.Expression):return walk(n.body,depth+1)
        if isinstance(n,ast.Name) and n.id=='x':return x
        if isinstance(n,ast.Constant) and type(n.value) is int and abs(n.value)<=100:return n.value
        if isinstance(n,ast.BinOp) and type(n.op) in (ast.Add,ast.Sub,ast.Mult):
            a,b=walk(n.left,depth+1),walk(n.right,depth+1)
            value=a+b if isinstance(n.op,ast.Add) else a-b if isinstance(n.op,ast.Sub) else a*b
            if abs(value)>1000000:raise ValueError('expression magnitude')
            return value
        raise ValueError('unsupported expression syntax')
    return walk(node)

def score(row,raw):
    if row['task']!='expression':return raw==row['answer'].encode('utf-8')
    try:
        s=raw.decode('utf-8')
        if '\n' in s or '\r' in s:return False
        return all(expression(s,x)==expression(row['answer'],x) for x in (-5,-1,0,2,7))
    except (ValueError,SyntaxError,UnicodeError,TypeError,RecursionError):return False

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'data/instructions_v07');a=p.parse_args()
    print(json.dumps(write_dataset(a.out),indent=2))
