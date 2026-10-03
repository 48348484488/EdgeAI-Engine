#!/usr/bin/env python3
"""Evaluate the complete EdgeAI router/tool path on the sealed v0.15 range."""
import argparse,json,re,subprocess,time
from pathlib import Path

META=re.compile(r'^\[route=([a-z_]+) neural=(0|1) loops=(\d+) token_score=([^\]]+)\]$')

def parse_meta(line):
    m=META.match(line)
    if not m:
        raise ValueError('invalid chat metadata: '+line)
    return dict(route=m.group(1),neural_used=m.group(2)=='1',
                loops=int(m.group(3)),token_score=float(m.group(4)))

def run_case(chat,row):
    t0=time.perf_counter()
    p=subprocess.run([str(chat),'--memory',':memory:','--prompt',row['prompt']],
                     capture_output=True,text=True,timeout=10)
    wall=time.perf_counter()-t0
    if p.returncode:
        raise RuntimeError(p.stderr or 'edgeai_chat failed')
    lines=p.stdout.rstrip('\n').splitlines()
    if len(lines)<2:
        raise RuntimeError('missing chat metadata')
    try:
        meta=parse_meta(lines[-1])
    except ValueError as error:
        raise RuntimeError(str(error)) from error
    answer='\n'.join(lines[:-1])
    return dict(id=row['id'],task=row['task'],prompt=row['prompt'],expected=row['answer'],
                actual=answer,exact=answer==row['answer'],route=meta['route'],
                neural_used=meta['neural_used'],loops=meta['loops'],
                token_score=meta['token_score'],wall_seconds=wall)

def summarize(rows):
    routes={}
    for x in rows:
        routes[x['route']]=routes.get(x['route'],0)+1
    return dict(count=len(rows),correct=sum(x['exact'] for x in rows),
                tool_cases=sum(not x['neural_used'] for x in rows),
                neural_cases=sum(x['neural_used'] for x in rows),
                tool_correct=sum(x['exact'] and not x['neural_used'] for x in rows),
                neural_correct=sum(x['exact'] and x['neural_used'] for x in rows),
                routes=routes)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--chat',type=Path,required=True)
    p.add_argument('--data',type=Path,default=Path('data/instructions_v015/test_range.jsonl'))
    p.add_argument('--out',type=Path,default=Path('results/v015/hybrid_system.json'))
    a=p.parse_args()
    rows=[json.loads(x) for x in a.data.read_text().splitlines() if x.strip()]
    cases=[run_case(a.chat.resolve(),r) for r in rows]
    tasks={t:summarize([x for x in cases if x['task']==t]) for t in sorted({x['task'] for x in cases})}
    split=a.data.stem
    report=dict(
        protocol=f'complete EdgeAI router/tool evaluation on sealed v0.15 {split}',
        split=split,
        caveat='system capability benchmark; deterministic tool successes are not neural generalization',
        summary=summarize(cases),by_task=tasks,cases=cases)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(dict(summary=report['summary'],by_task=tasks)))

if __name__=='__main__':main()
