"""v0.15 boundary-shift curriculum with a preregistered fresh extrapolation range."""
from pathlib import Path
import itertools,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import build_dataset,validate_dataset,dumps,sha

def _sample_strings(length,count,label):
    xs=(''.join(x) for x in itertools.product('abcdef',repeat=length))
    return sorted(xs,key=lambda s:sha((label+s).encode()))[:count]

def build_v015():
    data=build_dataset()
    # v0.12 test_range is retired for this version because its numeric/string
    # boundary informed the new curriculum. v0.15 gets a new sealed range below.
    data['test_range']=[]
    existing={(r['prompt'],r['answer']) for split,rows in data.items() for r in rows for split in [split]}
    def add(split,task,group,prompt,answer,language,template):
        key=(prompt,answer)
        if key in existing: return
        row=dict(task=task,group=group,prompt=prompt,answer=answer,
                 language=language,template=template)
        row['id']=sha(dumps(row).encode())[:20]
        data[split].append(row);existing.add(key)

    # Train-only boundary expansion: strings 5-6, addition operands through 39,
    # expression coefficients through 49. Reverse remains a held-out family.
    for length in (5,6):
        for s in _sample_strings(length,256,f'v015-train-string-{length}:'):
            g=f'v015-string:{s}'
            add('train','copy',g,f'Copy exactly: {s}',s,'en','copy_en_v015')
            add('train','copy',g,f'Copie exatamente: {s}',s,'pt','copy_pt_v015')
            add('train','uppercase',g,f'Uppercase: {s}',s.upper(),'en','uppercase_en_v015')
            add('train','uppercase',g,f'Maiusculas: {s}',s.upper(),'pt','uppercase_pt_v015')
    for a in range(20,40):
        for b in range(0,40):
            g=f'v015-pair:{min(a,b)}:{max(a,b)}:{a}:{b}'
            add('train','addition',g,f'Add: {a} + {b}',str(a+b),'en','addition_en_v015')
            add('train','addition',g,f'Some: {a} + {b}',str(a+b),'pt','addition_pt_v015')
    for k in range(30,50):
        for op in ('+','-','*'):
            g=f'v015-coef:{k}:{op}'
            add('train','expression',g,f'Expression for x {op} {k}:',f'x{op}{k}','en','expression_en_v015')
            add('train','expression',g,f'Expressao para x {op} {k}:',f'x{op}{k}','pt','expression_pt_v015')

    # Fresh sealed v0.15 range: deliberately beyond all train-only expansions.
    for s in _sample_strings(7,16,'v015-holdout-string:'):
        g=f'v015-holdout-string:{s}'
        add('test_range','copy',g,f'Copy exactly: {s}',s,'en','copy_en_v015_holdout')
        add('test_range','copy',g,f'Copie exatamente: {s}',s,'pt','copy_pt_v015_holdout')
        add('test_range','uppercase',g,f'Uppercase: {s}',s.upper(),'en','uppercase_en_v015_holdout')
        add('test_range','uppercase',g,f'Maiusculas: {s}',s.upper(),'pt','uppercase_pt_v015_holdout')
    pairs=sorted(itertools.combinations_with_replacement(range(40,50),2),
                 key=lambda p:sha((f'v015-holdout-pair:{p[0]}:{p[1]}').encode()))[:16]
    for a,b in pairs:
        g=f'v015-holdout-pair:{a}:{b}'
        add('test_range','addition',g,f'Add: {a} + {b}',str(a+b),'en','addition_en_v015_holdout')
        add('test_range','addition',g,f'Some: {a} + {b}',str(a+b),'pt','addition_pt_v015_holdout')
    expr=sorted(((k,op) for k in range(50,60) for op in ('+','-','*')),
                key=lambda x:sha((f'v015-holdout-expr:{x[0]}:{x[1]}').encode()))[:16]
    for k,op in expr:
        g=f'v015-holdout-expr:{k}:{op}'
        add('test_range','expression',g,f'Expression for x {op} {k}:',f'x{op}{k}','en','expression_en_v015_holdout')
        add('test_range','expression',g,f'Expressao para x {op} {k}:',f'x{op}{k}','pt','expression_pt_v015_holdout')

    for split in data:
        data[split]=sorted(data[split],key=lambda r:r['id'])
    validate_dataset(data)
    return data

def main():
    out=ROOT/'data/instructions_v015';out.mkdir(parents=True,exist_ok=True)
    data=build_v015();files={}
    for split,rows in data.items():
        raw=('\n'.join(dumps(r) for r in rows)+'\n').encode()
        (out/(split+'.jsonl')).write_bytes(raw)
        files[split+'.jsonl']=dict(sha256=sha(raw),rows=len(rows),bytes=len(raw))
    manifest=dict(format='edge-sft-synthetic-1',synthetic=True,
        source='deterministic local rules; v0.15 boundary-shift curriculum',
        license='CC0-1.0',generator_sha256=sha(Path(__file__).read_bytes()),files=files,
        preregistered_holdout=dict(strings='length 7',addition='operands 40-49',expression='coefficients 50-59'),
        limitations=[
          'v0.12 test_range informed this curriculum and is retired for v0.15 claims',
          'v0.15 test_range is generated before training and never used for checkpoint selection',
          'reverse remains a fully held-out family',
          'synthetic diagnostic curriculum, not a standardized benchmark'])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))
if __name__=='__main__':main()
