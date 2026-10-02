#!/usr/bin/env python3
"""Native evaluation for the stabilized v0.13 length-bridge candidate."""
import argparse,json,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha,score
from instruction_blocks_eval_v012 import summarize

def validate_candidate(r):
    runs=r.get('runs',[])
    if r.get('completed')!=3 or r.get('expected')!=3:return False
    return {(x.get('seed'),x.get('blocks')) for x in runs}=={(11,2),(22,2),(33,2)}

def task_range(examples):
    out={}
    for task in sorted({x['task'] for x in examples}):
        rows=[x for x in examples if x['task']==task]
        out[task]=dict(correct=sum(bool(x['correct']) for x in rows),count=len(rows))
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,default=ROOT/'build')
    p.add_argument('--training',type=Path,default=ROOT/'results/v013_length_stabilized/training.json')
    p.add_argument('--baseline',type=Path,default=ROOT/'results/v013_length/evaluation.json')
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v013_length')
    p.add_argument('--out',type=Path,default=ROOT/'results/v013_length_stabilized/evaluation.json');a=p.parse_args()
    t=json.loads(a.training.read_text());base=json.loads(a.baseline.read_text())
    if not validate_candidate(t):raise ValueError('candidate report incomplete')
    data,_=load_dataset(a.data);digest=sha((a.data/'manifest.json').read_bytes())
    if digest!=t['dataset_sha256'] or digest!=base['dataset_sha256']:raise ValueError('dataset mismatch')
    binary=a.build.resolve()/'edgeai_generate'
    base_map={(r['seed'],r['blocks']):r for r in base['runs']};runs=[];examples=[];pairs=[]
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for tr in sorted(t['runs'],key=lambda x:x['seed']):
            model=(ROOT/tr['model_path']).resolve()
            if not model.is_file() or sha(model.read_bytes())!=tr['model_sha256']:raise ValueError('candidate model mismatch')
            rows=[]
            for split in ('test_id','test_template','test_range','test_family'):
                for ex in data[split]:
                    pp=td/'p';aa=td/'a';pp.write_bytes(ex['prompt'].encode())
                    st=time.perf_counter();proc=subprocess.run([str(binary),str(model),str(pp),str(aa),'32'],capture_output=True,text=True,timeout=20);wall=time.perf_counter()-st
                    if proc.returncode:raise RuntimeError(proc.stderr or 'generation failed')
                    raw=aa.read_bytes();metrics=json.loads(proc.stdout)
                    row=dict(ex,split=split,seed=tr['seed'],blocks=2,actual=raw.decode(errors='replace'),actual_hex=raw.hex(),
                        exact=raw==ex['answer'].encode(),correct=score(ex,raw),external_wall_seconds=wall,**metrics)
                    rows.append(row);examples.append(row)
            run=dict(seed=tr['seed'],blocks=2,summary=summarize(rows),
                by_split={s:summarize([x for x in rows if x['split']==s]) for s in ('test_id','test_template','test_range','test_family')},
                by_task={k:summarize([x for x in rows if x['task']==k]) for k in sorted({x['task'] for x in rows})},
                selected_validation_nll=tr['selected_validation_nll'],selected_step=tr['selected_step'],train_cpu_seconds=tr['train_cpu_seconds'])
            runs.append(run)
            one=base_map[(tr['seed'],1)];rnd=base_map[(tr['seed'],2)]
            rr=[x for x in rows if x['split']=='test_range'];base_examples=[x for x in base['examples'] if x['seed']==tr['seed'] and x['blocks']==2 and x['split']=='test_range']
            pairs.append(dict(seed=tr['seed'],one_total=one['summary']['correct'],random_two_total=rnd['summary']['correct'],candidate_total=run['summary']['correct'],
                one_range=one['by_split']['test_range']['correct'],random_two_range=rnd['by_split']['test_range']['correct'],candidate_range=run['by_split']['test_range']['correct'],
                random_range_tasks=task_range(base_examples),candidate_range_tasks=task_range(rr)))
    report=dict(protocol='stabilized two-block candidate versus frozen v0.13 length-bridge baselines',
        dataset_sha256=digest,training_sha256=sha(a.training.read_bytes()),runs=runs,pairs=pairs,examples=examples,
        candidate_total=sum(x['candidate_total'] for x in pairs),random_two_total=sum(x['random_two_total'] for x in pairs),
        one_total=sum(x['one_total'] for x in pairs),candidate_range_total=sum(x['candidate_range'] for x in pairs),
        random_two_range_total=sum(x['random_two_range'] for x in pairs))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:report[k] for k in ('candidate_total','random_two_total','one_total','candidate_range_total','random_two_range_total')}))
if __name__=='__main__':main()
