#!/usr/bin/env python3
"""Native, unassisted instruction evaluation; exact correctness is not EOS rate."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import load_dataset,sha,score

def summarize(rows):
    n=len(rows)
    return dict(count=n,exact=sum(r['exact'] for r in rows),correct=sum(r['correct'] for r in rows),
                eos=sum(r['stopped_on_eos'] for r in rows),correct_and_eos=sum(r['correct'] and r['stopped_on_eos'] for r in rows),
                median_generated_tokens=statistics.median(r['generated_tokens'] for r in rows) if n else None,
                median_internal_seconds=statistics.median(r['total_seconds'] for r in rows) if n else None)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--report',type=Path,default=ROOT/'results/v07/training.json');p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07');p.add_argument('--out',type=Path,default=ROOT/'results/v07/evaluation.json');a=p.parse_args()
    data,manifest=load_dataset(a.data);training=json.loads(a.report.read_text());rows_out=[];runs=[];started=time.perf_counter()
    if training.get('completed')!=training['expected']:raise ValueError('training incomplete')
    if sha((a.data/'manifest.json').read_bytes())!=training['dataset_sha256']:raise ValueError('dataset differs from training')
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for trial in training['runs']:
            for phase in ('before','after'):
                model=(ROOT/trial[phase+'_path']).resolve()
                if not model.is_relative_to(ROOT) or sha(model.read_bytes())!=trial['artifacts'][trial[phase+'_path']]:raise ValueError('model artifact mismatch')
                rows=[]
                for split in ('test_id','test_template','test_range','test_family'):
                    for example in data[split]:
                        (td/'prompt').write_bytes(example['prompt'].encode());start=time.perf_counter()
                        proc=subprocess.run([str(a.build.resolve()/'edgeai_generate'),str(model),str(td/'prompt'),str(td/'answer'),'32'],capture_output=True,text=True,timeout=20)
                        if proc.returncode:raise RuntimeError(proc.stderr)
                        external=time.perf_counter()-start;metrics=json.loads(proc.stdout);raw=(td/'answer').read_bytes()
                        row=dict(example,split=split,seed=trial['seed'],phase=phase,actual=raw.decode('utf-8',errors='replace'),actual_hex=raw.hex(),
                                 exact=raw==example['answer'].encode(),correct=score(example,raw),external_wall_seconds=external,**metrics)
                        rows.append(row)
                result=dict(seed=trial['seed'],phase=phase,model_path=str(model.relative_to(ROOT)),summary=summarize(rows),
                            by_split={s:summarize([r for r in rows if r['split']==s]) for s in ('test_id','test_template','test_range','test_family')},
                            by_task={t:summarize([r for r in rows if r['task']==t]) for t in sorted({r['task'] for r in rows})},
                            by_language={t:summarize([r for r in rows if r['language']==t]) for t in ('en','pt')})
                rows_out.extend(rows);runs.append(result);print(json.dumps({k:result[k] for k in ('seed','phase','summary')}),flush=True)
    report=dict(protocol='native C++ greedy; 32 tokens including EOS; no model tools or deterministic shortcut',
                metric='exact raw bytes except restricted expression correctness on five x values; exact reported separately; combined correctness and EOS also reported',
                training_report_sha256=sha(a.report.read_bytes()),dataset_sha256=sha((a.data/'manifest.json').read_bytes()),
                runs=runs,examples=rows_out,completed=len(runs),wall_seconds=time.perf_counter()-started,energy_joules=None,
                caveats=['synthetic diagnostic tasks, not an independent general-assistant benchmark','before phase is same pretrained checkpoint expanded with two initially untrained special IDs','test_range changes lengths/magnitudes; test_family reversal has no training examples','timings include model load and may cover wrong or empty outputs; not latency per useful response'])
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
if __name__=='__main__':main()
