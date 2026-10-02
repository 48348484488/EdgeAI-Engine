#!/usr/bin/env python3
"""Refuse incomplete or inconsistent research reports. Does not claim utility."""
import argparse,json
from pathlib import Path
from external_data import ROOT,sha,load_snapshot

def validate(directory):
    d=Path(directory);report=json.loads((d/'training.json').read_text());n=json.loads((d/'native.json').read_text());c=json.loads((d/'capability.json').read_text());e=json.loads((d/'energy.json').read_text());p=json.loads((d/'parity.json').read_text());load_snapshot(ROOT/'data/cpython_snapshot')
    if report['completed']!=report['expected'] or len(report['runs'])!=report['expected']:raise ValueError('incomplete training trials')
    identities=set()
    for row in report['runs']:
        key=(row['kind'],row['seed'])
        if key in identities:raise ValueError('duplicate trial')
        identities.add(key)
        for f,h in row['artifacts'].items():
            path=(ROOT/f).resolve()
            if not path.is_relative_to(ROOT) or sha(path.read_bytes())!=h:raise ValueError('artifact integrity failure')
        if row['metrics']['raw_bytes']!=report['test_raw_bytes']:raise ValueError('different raw texts scored')
        if not row['train_cpu_seconds']>=report['cpu_budget_seconds']:raise ValueError('training budget not reached')
    if p.get('all_passed') is not True or len(n['parity'])!=report['expected'] or not all(x['passed'] for x in n['parity']):raise ValueError('native parity incomplete')
    if len(n['rows'])!=n['repeats']*report['expected'] or len(c['neural'])!=report['expected']:raise ValueError('native or task report incomplete')
    if c['exact_prompts_found_in_train']:raise ValueError('task leakage')
    if e['exit_code']!=0 or (not e['available'] and e['package_energy_joules'] is not None):raise ValueError('invalid energy report')
    return dict(status='passed',models=report['expected'],native_repetitions=len(n['rows']),tasks_per_model=c['task_count'],energy_available=e['available'],note='Research artifacts consistent; this status does NOT indicate task quality or frontier-level ability.')

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=ROOT/'results/v06');a=p.parse_args();r=validate(a.directory);(a.directory/'validated.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
