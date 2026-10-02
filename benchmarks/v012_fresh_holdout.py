#!/usr/bin/env python3
"""Fresh post-hoc holdout for the frozen v0.12 baseline and depth candidate."""
import argparse,itertools,json,statistics,subprocess,sys,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import load_dataset,sha,dumps,score

def fresh_rows():
    rows=[]
    def add(task,group,values,answer):
        templates={
            'copy':('Copy exactly: {s}','Copie exatamente: {s}'),
            'uppercase':('Uppercase: {s}','Maiusculas: {s}'),
            'addition':('Add: {a} + {b}','Some: {a} + {b}'),
            'expression':('Expression for x {op} {k}:','Expressao para x {op} {k}:'),
        }[task]
        for lang,t in zip(('en','pt'),templates):
            row=dict(task=task,group=group,prompt=t.format(**values),answer=answer,
                     language=lang,template=f'fresh_{task}_{lang}')
            row['id']=sha(dumps(row).encode())[:20];rows.append(row)
    strings=sorted((''.join(x) for x in itertools.product('abcdef',repeat=5)),
                   key=lambda s:sha(('fresh-string:'+s).encode()))[:16]
    for s in strings:
        add('copy','fresh-string:'+s,dict(s=s),s)
        add('uppercase','fresh-string:'+s,dict(s=s),s.upper())
    pairs=sorted(itertools.combinations_with_replacement(range(20,30),2),
                 key=lambda p:sha((f'fresh-pair:{p[0]}:{p[1]}').encode()))[:16]
    for a,b in pairs:
        add('addition',f'fresh-pair:{a}:{b}',dict(a=a,b=b),str(a+b))
    expr=sorted(((k,op) for k in range(30,40) for op in ('+','-','*')),
                key=lambda x:sha((f'fresh-expr:{x[0]}:{x[1]}').encode()))[:16]
    for k,op in expr:
        add('expression',f'fresh-expr:{k}:{op}',dict(k=k,op=op),f'x{op}{k}')
    return rows

def validate_fresh(rows,data_dir):
    data,_=load_dataset(Path(data_dir))
    old_prompts={r['prompt'] for split in data.values() for r in split}
    old_groups={r['group'] for split in data.values() for r in split}
    if len(rows)!=128 or len({r['id'] for r in rows})!=128: raise ValueError('fresh holdout size/id contract')
    if any(r['prompt'] in old_prompts or r['group'] in old_groups for r in rows):
        raise ValueError('fresh holdout overlaps frozen v0.7 inputs')
    return True

def summarize(rows):
    return dict(count=len(rows),exact=sum(r['exact'] for r in rows),correct=sum(r['correct'] for r in rows),
                eos=sum(r['stopped_on_eos'] for r in rows),
                median_internal_seconds=statistics.median(r['total_seconds'] for r in rows))

def eval_model(binary,model,rows,seed,blocks):
    out=[]
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);prompt=td/'prompt';answer=td/'answer'
        for ex in rows:
            prompt.write_bytes(ex['prompt'].encode())
            proc=subprocess.run([str(binary),str(model),str(prompt),str(answer),'32'],
                                capture_output=True,text=True,timeout=20)
            if proc.returncode: raise RuntimeError(proc.stderr or 'native generation failed')
            metrics=json.loads(proc.stdout);raw=answer.read_bytes()
            out.append(dict(ex,seed=seed,blocks=blocks,actual=raw.decode('utf-8',errors='replace'),
                            exact=raw==ex['answer'].encode(),correct=score(ex,raw),**metrics))
    return out

def resolve_trial(root,row):
    rel=row.get('after_path') or row.get('model_path')
    dig=(row.get('artifacts') or {}).get(rel) or row.get('model_sha256')
    p=(Path(root)/rel).resolve()
    if not p.is_file(): raise FileNotFoundError(str(p))
    if dig and sha(p.read_bytes())!=dig: raise ValueError('model hash mismatch: '+rel)
    return p

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True)
    p.add_argument('--baseline-root',type=Path,required=True);p.add_argument('--candidate-root',type=Path,required=True)
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    p.add_argument('--out',type=Path,default=ROOT/'results/v012_fresh_holdout/evaluation.json');a=p.parse_args()
    rows=fresh_rows();validate_fresh(rows,a.data);binary=(a.build/'edgeai_generate').resolve()
    bt=json.loads((a.baseline_root/'results/v012/training.json').read_text())
    ct=json.loads((a.candidate_root/'results/v012_copy_init_low_lr/training.json').read_text())
    br={r['seed']:r for r in bt['runs'] if r['blocks']==1};cr={r['seed']:r for r in ct['runs']}
    runs=[];pairs=[];examples=[]
    for seed in (11,22,33):
        one=eval_model(binary,resolve_trial(a.baseline_root,br[seed]),rows,seed,1)
        two=eval_model(binary,resolve_trial(a.candidate_root,cr[seed]),rows,seed,2)
        s1,s2=summarize(one),summarize(two);examples.extend(one);examples.extend(two)
        runs.extend([dict(seed=seed,blocks=1,summary=s1),dict(seed=seed,blocks=2,summary=s2)])
        pairs.append(dict(seed=seed,one_exact=s1['exact'],two_exact=s2['exact'],exact_delta=s2['exact']-s1['exact'],
                          one_correct=s1['correct'],two_correct=s2['correct'],correct_delta=s2['correct']-s1['correct']))
    report=dict(protocol='fresh post-hoc unused-range holdout; frozen models only; no retraining',
                construction='16 unseen groups each for strings, addition 20-29 and expression coefficients 30-39; familiar base templates',
                caveat='constructed after the original v0.12 tests were observed; useful replication evidence, not a pre-registered benchmark',
                count=len(rows),pairs=pairs,runs=runs,
                one_exact=sum(x['one_exact'] for x in pairs),two_exact=sum(x['two_exact'] for x in pairs),
                one_correct=sum(x['one_correct'] for x in pairs),two_correct=sum(x['two_correct'] for x in pairs),
                two_wins=sum(x['exact_delta']>0 for x in pairs),one_wins=sum(x['exact_delta']<0 for x in pairs),
                ties=sum(x['exact_delta']==0 for x in pairs),examples=examples)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:report[k] for k in ('one_exact','two_exact','one_correct','two_correct','two_wins','one_wins','ties')}))

if __name__=='__main__':main()
