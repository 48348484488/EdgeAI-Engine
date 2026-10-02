#!/usr/bin/env python3
"""Integrity gates, not a gate claiming model intelligence from test pass counts."""
import argparse
import json
from pathlib import Path
from instruction_data import load_dataset,build_dataset,sha
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=ROOT/'results/v07');p.add_argument('--data-only',action='store_true');a=p.parse_args()
    data,manifest=load_dataset(ROOT/'data/instructions_v07')
    if manifest['generator_sha256']!=sha((ROOT/'tools/instruction_data.py').read_bytes()):raise ValueError('generator changed after snapshot')
    if data!=build_dataset():raise ValueError('dataset not reproducible')
    if a.data_only:print('Synthetic data reproducible, hashes and disjoint groups verified.');return
    train=json.loads((a.directory/'training.json').read_text());ev=json.loads((a.directory/'evaluation.json').read_text());parity=json.loads((a.directory/'parity.json').read_text())
    if train.get('completed')!=train['expected'] or ev['completed']!=2*train['expected']:raise ValueError('missing trial')
    digest=sha((a.directory/'training.json').read_bytes())
    if any(r['training_report_sha256']!=digest for r in (ev,parity)):raise ValueError('stale evidence')
    legacy=json.loads((a.directory/'legacy_diagnostic.json').read_text())
    if legacy['training_report_sha256']!=digest or len(legacy['runs'])!=2*train['expected']:raise ValueError('legacy diagnostic incomplete/stale')
    if not parity['all_passed']:raise ValueError('parity failed')
    expected=sum(len(data[s]) for s in ('test_id','test_template','test_range','test_family'))
    for row in ev['runs']:
        if row['summary']['count']!=expected:raise ValueError('evaluation missing examples')
    for row in train['runs']:
        for name,digest in row['artifacts'].items():
            path=(ROOT/name).resolve()
            if not path.is_relative_to(ROOT) or sha(path.read_bytes())!=digest:raise ValueError('artifact checksum mismatch')
    output=dict(validated=True,training_runs=train['completed'],evaluated_phases=ev['completed'],examples_per_phase=expected,
                logit_cases=len(parity['logit_cases']),greedy_cases=len(parity['greedy_cases']),energy_claim=False)
    (a.directory/'validation.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output))
if __name__=='__main__':main()
