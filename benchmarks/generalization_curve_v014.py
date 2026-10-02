#!/usr/bin/env python3
"""Post-hoc generalization curves for frozen v0.13 BPE and v0.14 byte models.

Diagnostic only: these probes are never used for training or checkpoint selection.
"""
import argparse,json,subprocess,tempfile
from pathlib import Path

def string_for(length,i):
    n=(i*7919+length*104729)%(6**length)
    chars=[]
    for _ in range(length):
        chars.append("abcdef"[n%6]);n//=6
    return ''.join(reversed(chars))

def probes():
    rows=[]
    for length in range(1,9):
        for i in range(12):
            s=string_for(length,i)
            rows.append(dict(axis='string_length',bucket=length,task='copy',prompt='Copy exactly: '+s,answer=s))
            rows.append(dict(axis='string_length',bucket=length,task='uppercase',prompt='Uppercase: '+s,answer=s.upper()))
            rows.append(dict(axis='reverse_length',bucket=length,task='reverse',prompt='Reverse: '+s,answer=s[::-1]))
    for base in (0,10,20,30,40):
        for i in range(16):
            a=base+(i*3)%10;b=base+(i*7+1)%10
            rows.append(dict(axis='addition_band',bucket=f'{base}-{base+9}',task='addition',
                             prompt=f'Add: {a} + {b}',answer=str(a+b)))
    for base in (0,10,20,30,40,50):
        for op in ('+','-','*'):
            for i in range(4):
                k=base+(i*3)%10
                rows.append(dict(axis='expression_band',bucket=f'{base}-{base+9}',task='expression',
                                 prompt=f'Expression for x {op} {k}:',answer=f'x{op}{k}'))
    return rows

def evaluate(binary,model,rows):
    out=[]
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);pp=td/'prompt';ap=td/'answer'
        for row in rows:
            pp.write_text(row['prompt']);ap.write_bytes(b'')
            proc=subprocess.run([str(binary),str(model),str(pp),str(ap),'32'],
                                capture_output=True,text=True,timeout=20)
            if proc.returncode: raise RuntimeError(proc.stderr or 'native generation failed')
            actual=ap.read_text(errors='replace')
            out.append(dict(row,actual=actual,correct=actual==row['answer']))
    return out

def summarize(rows):
    buckets={}
    for r in rows:
        key=(r['axis'],str(r['bucket']),r['task'])
        x=buckets.setdefault(key,dict(count=0,correct=0))
        x['count']+=1;x['correct']+=int(r['correct'])
    return [dict(axis=a,bucket=b,task=t,**v) for (a,b,t),v in sorted(buckets.items())]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--build',type=Path,default=Path('build'))
    p.add_argument('--out',type=Path,default=Path('results/v014/generalization_curve.json'))
    a=p.parse_args();binary=(a.build/'edgeai_generate').resolve()
    specs=[]
    for family,root,suffix in (
        ('bpe-v013',Path('models/v013'),'-after.edge'),
        ('byte-v014',Path('models/v014'),'-byte-after.edge')):
        for seed in (11,22,33):
            for blocks in (1,2):
                name=f'seed{seed}-b{blocks}{suffix}'
                specs.append((family,seed,blocks,root/name))
    rows=probes();runs=[]
    for family,seed,blocks,model in specs:
        if not model.is_file(): raise FileNotFoundError(model)
        examples=evaluate(binary,model,rows)
        runs.append(dict(family=family,seed=seed,blocks=blocks,model=str(model),
                         summary=summarize(examples)))
        print(json.dumps(dict(family=family,seed=seed,blocks=blocks,done=len(examples))),flush=True)
    report=dict(protocol='post-hoc frozen-model boundary curve; never used for training or checkpoint selection',
                probes_per_model=len(rows),runs=runs)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
