#!/usr/bin/env python3
"""Diagnose why v0.12 depth changes do or do not improve native generation."""
import argparse,json,statistics
from pathlib import Path

def diagnose(training,evaluation):
    tr={(r['seed'],r['blocks']):r for r in training['runs']}
    ev={(r['seed'],r['blocks']):r for r in evaluation['runs']}
    seeds=sorted(set(s for s,b in tr) & set(s for s,b in ev))
    pairs=[]
    for seed in seeds:
        a,b=tr[(seed,1)],tr[(seed,2)]
        ea,eb=ev[(seed,1)],ev[(seed,2)]
        pairs.append(dict(
            seed=seed,
            one_correct=ea['summary']['correct'],two_correct=eb['summary']['correct'],
            correct_delta=eb['summary']['correct']-ea['summary']['correct'],
            one_validation_nll=a['selected_validation_nll'],two_validation_nll=b['selected_validation_nll'],
            validation_nll_delta=b['selected_validation_nll']-a['selected_validation_nll'],
            one_steps=a['steps'],two_steps=b['steps'],
            two_step_ratio=b['steps']/a['steps'],
            one_internal_seconds=ea['summary']['median_internal_seconds'],
            two_internal_seconds=eb['summary']['median_internal_seconds'],
            latency_ratio=eb['summary']['median_internal_seconds']/ea['summary']['median_internal_seconds'],
        ))
    one=sum(x['one_correct'] for x in pairs);two=sum(x['two_correct'] for x in pairs)
    n=sum(ev[(s,1)]['summary']['count'] for s in seeds)
    return dict(
        seeds=seeds,cases_per_architecture=n,
        one_correct=one,two_correct=two,correct_delta=two-one,
        two_wins=sum(x['correct_delta']>0 for x in pairs),
        one_wins=sum(x['correct_delta']<0 for x in pairs),
        ties=sum(x['correct_delta']==0 for x in pairs),
        median_two_step_ratio=statistics.median(x['two_step_ratio'] for x in pairs),
        median_latency_ratio=statistics.median(x['latency_ratio'] for x in pairs),
        validation_prefers_two=sum(x['validation_nll_delta']<0 for x in pairs),
        generation_prefers_two=sum(x['correct_delta']>0 for x in pairs),
        pairs=pairs,
        findings=[
            'equal CPU time does not imply equal optimizer updates: the two-block model completes fewer steps',
            'validation NLL and greedy exact/correct generation are not interchangeable selection objectives',
            'the second block starts function-preserving, so the comparison isolates learned depth rather than an initial output shift',
        ],
    )

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--training',type=Path,default=Path('results/v012/training.json'))
    p.add_argument('--evaluation',type=Path,default=Path('results/v012/evaluation.json'))
    p.add_argument('--out',type=Path,default=Path('results/v012/depth_diagnosis.json'))
    a=p.parse_args()
    d=diagnose(json.loads(a.training.read_text()),json.loads(a.evaluation.read_text()))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(d,indent=2)+'\n')
    print(json.dumps(d))

if __name__=='__main__': main()
