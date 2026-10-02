#!/usr/bin/env python3
"""Supplementary transfer audit on the 28 unchanged v0.6 authored prompts.

Added after the frozen main v0.7 evaluation, not used for model selection. Uses
original v0.6 scoring rules (arithmetic/copy strip whitespace; code first line),
with the same v0.7 32-token limit and EOS for paired before/after models.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import load_dataset,sha
from capability_v06 import tasks,score_task

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--report',type=Path,default=ROOT/'results/v07/training.json');p.add_argument('--out',type=Path,default=ROOT/'results/v07/legacy_diagnostic.json');a=p.parse_args()
    data,_=load_dataset(ROOT/'data/instructions_v07');suite=tasks();tr=json.loads(a.report.read_text());rows=[]
    if any(t['prompt']==r['prompt'] for t in suite for r in data['train']):raise ValueError('legacy exact prompt leaked')
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for trial in tr['runs']:
            for phase in ('before','after'):
                model=ROOT/trial[phase+'_path']
                if sha(model.read_bytes())!=trial['artifacts'][trial[phase+'_path']]:raise ValueError('model changed')
                results=[]
                for t in suite:
                    (td/'prompt').write_bytes(t['prompt'].encode())
                    meta=json.loads(subprocess.check_output([str(a.build.resolve()/'edgeai_generate'),str(model),str(td/'prompt'),str(td/'out'),'32'],text=True,timeout=20))
                    raw=(td/'out').read_bytes();results.append(dict(task=t['id'],category=t['category'],passed=score_task(t,raw),stopped_on_eos=meta['stopped_on_eos'],raw_hex=raw.hex(),text=raw.decode('utf-8','replace')))
                rows.append(dict(seed=trial['seed'],phase=phase,correct=sum(r['passed'] for r in results),eos=sum(r['stopped_on_eos'] for r in results),count=len(results),results=results))
                print(json.dumps({k:rows[-1][k] for k in ('seed','phase','correct','eos','count')}),flush=True)
    report=dict(supplementary=True,used_for_selection=False,prompts=suite,training_report_sha256=sha(a.report.read_bytes()),runs=rows,
                note='Original v0.6 prompt/scorer only; v0.7 uses learned EOS and a 32-token cap versus original 48. Pair before/after here, not an identical rerun of the v0.6 protocol. No tools.')
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
