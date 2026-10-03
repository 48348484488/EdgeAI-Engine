#!/usr/bin/env python3
"""Summarize v0.12 failures by held-out split/task without using test data for checkpoint selection."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def compact(path):
    j=json.loads(path.read_text());out=[]
    for r in j['runs']:
        out.append(dict(seed=r['seed'],blocks=r['blocks'],lr=r.get('lr'),
          correct=r['summary']['correct'],count=r['summary']['count'],
          by_split={k:dict(correct=v['correct'],count=v['count']) for k,v in r.get('by_split',{}).items()},
          by_task={k:dict(correct=v['correct'],count=v['count']) for k,v in r.get('by_task',{}).items()}))
    return out
def main():
    base=compact(ROOT/'results/v012/evaluation.json')
    eq=compact(ROOT/'results/v012_equal_steps/evaluation.json')
    report=dict(
      purpose='diagnostic only; test splits are not checkpoint-selection data',
      baseline=base,equal_updates=eq,
      observations=[
        'held-out range and family splits expose generalization beyond memorized/base templates',
        'aggregate exact/correct alone can hide task-specific collapse',
        'next training experiments must keep these test splits sealed until final evaluation'])
    out=ROOT/'results/v012/generalization_diagnosis.json'
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
if __name__=='__main__':main()
