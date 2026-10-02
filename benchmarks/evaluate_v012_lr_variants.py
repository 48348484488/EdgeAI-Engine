#!/usr/bin/env python3
"""Native generation evaluator for v0.12 LR variants sharing the same seed/blocks."""
import argparse,json,statistics,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import load_dataset,sha,score

TEST_SPLITS=('test_id','test_template','test_range','test_family')

def summarize(rows):
    return dict(count=len(rows),exact=sum(r['exact'] for r in rows),correct=sum(r['correct'] for r in rows),
                eos=sum(r['stopped_on_eos'] for r in rows),
                median_generated_tokens=statistics.median(r['generated_tokens'] for r in rows),
                median_internal_seconds=statistics.median(r['total_seconds'] for r in rows))

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,default=ROOT/'build')
    p.add_argument('--training',type=Path,default=ROOT/'results/v012_lr_ablation/training.json')
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    p.add_argument('--out',type=Path,default=ROOT/'results/v012_lr_ablation/evaluation.json');a=p.parse_args()
    binary=(a.build/'edgeai_generate').resolve()
    if not binary.is_file(): raise FileNotFoundError(binary)
    tr=json.loads(a.training.read_text());data,_=load_dataset(a.data)
    digest=sha((a.data/'manifest.json').read_bytes())
    if digest!=tr.get('dataset_sha256'): raise ValueError('dataset differs from LR training report')
    runs=[];examples=[];started=time.perf_counter()
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for trial in tr['runs']:
            model=(ROOT/trial['model_path']).resolve()
            if not model.is_relative_to(ROOT) or sha(model.read_bytes())!=trial['model_sha256']:
                raise ValueError('LR model missing or hash mismatch')
            rows=[]
            for split in TEST_SPLITS:
                for ex in data[split]:
                    prompt=td/'prompt';answer=td/'answer';prompt.write_bytes(ex['prompt'].encode())
                    proc=subprocess.run([str(binary),str(model),str(prompt),str(answer),'32'],capture_output=True,text=True,timeout=20)
                    if proc.returncode: raise RuntimeError(proc.stderr or 'native generation failed')
                    m=json.loads(proc.stdout);raw=answer.read_bytes()
                    row=dict(ex,split=split,seed=trial['seed'],blocks=trial['blocks'],lr=trial['lr'],
                             actual=raw.decode(errors='replace'),exact=raw==ex['answer'].encode(),
                             correct=score(ex,raw),**m)
                    rows.append(row);examples.append(row)
            result=dict(seed=trial['seed'],blocks=trial['blocks'],lr=trial['lr'],
                        selected_step=trial['selected_step'],selected_validation_nll=trial['selected_validation_nll'],
                        train_cpu_seconds=trial['train_cpu_seconds'],summary=summarize(rows),
                        by_task={t:summarize([r for r in rows if r['task']==t]) for t in sorted({r['task'] for r in rows})})
            runs.append(result);print(json.dumps(result),flush=True)
    out=dict(protocol='native greedy generation for same-seed two-block LR variants',dataset_sha256=digest,
             runs=runs,examples=examples,completed=len(runs),wall_seconds=time.perf_counter()-started)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2)+'\n')

if __name__=='__main__': main()
