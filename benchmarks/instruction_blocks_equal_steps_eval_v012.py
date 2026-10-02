#!/usr/bin/env python3
"""Evaluate the v0.12 equal-update two-block checkpoints against frozen one-block native results."""
import argparse,json,statistics,subprocess,sys,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha,score
from instruction_blocks_eval_v012 import summarize

def validate_training(report):
    runs=report.get('runs')
    if report.get('completed')!=3 or report.get('expected')!=3 or report.get('fairness_verified') is not True:
        raise ValueError('equal-update training report incomplete')
    if not isinstance(runs,list) or {(r.get('seed'),r.get('blocks')) for r in runs}!={(11,2),(22,2),(33,2)}:
        raise ValueError('equal-update run set invalid')
    return True

def baseline_one(baseline,seed):
    rows=[r for r in baseline.get('runs',[]) if r.get('seed')==seed and r.get('blocks')==1]
    if len(rows)!=1: raise ValueError('missing unique one-block native baseline')
    return rows[0]

def evaluate(build,training_path,baseline_eval_path,data_dir,out_path):
    build=Path(build).resolve();binary=build/'edgeai_generate'
    if not binary.is_file(): raise FileNotFoundError('missing native generator: '+str(binary))
    training_path=Path(training_path);baseline_eval_path=Path(baseline_eval_path)
    training=json.loads(training_path.read_text());baseline=json.loads(baseline_eval_path.read_text())
    validate_training(training)
    data,_=load_dataset(Path(data_dir));dataset_digest=sha((Path(data_dir)/'manifest.json').read_bytes())
    if dataset_digest!=training.get('dataset_sha256') or dataset_digest!=baseline.get('dataset_sha256'):
        raise ValueError('dataset mismatch')
    splits=('test_id','test_template','test_range','test_family');runs=[];examples=[];pairs=[]
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for trial in sorted(training['runs'],key=lambda r:r['seed']):
            seed=trial['seed'];model=(ROOT/trial['model_path']).resolve()
            if not model.is_relative_to(ROOT) or not model.is_file(): raise ValueError('equal-update model missing')
            if sha(model.read_bytes())!=trial['model_sha256']: raise ValueError('equal-update model hash mismatch')
            rows=[]
            for split in splits:
                for ex in data[split]:
                    prompt=td/'prompt';answer=td/'answer';prompt.write_bytes(ex['prompt'].encode())
                    start=time.perf_counter()
                    proc=subprocess.run([str(binary),str(model),str(prompt),str(answer),'32'],
                                        capture_output=True,text=True,timeout=20)
                    external=time.perf_counter()-start
                    if proc.returncode: raise RuntimeError(proc.stderr or 'native generation failed')
                    metrics=json.loads(proc.stdout);raw=answer.read_bytes()
                    row=dict(ex,split=split,seed=seed,blocks=2,actual=raw.decode('utf-8',errors='replace'),
                             actual_hex=raw.hex(),exact=raw==ex['answer'].encode(),correct=score(ex,raw),
                             external_wall_seconds=external,**metrics)
                    rows.append(row);examples.append(row)
            result=dict(seed=seed,blocks=2,model_path=trial['model_path'],
                        selected_validation_nll=trial['selected_validation_nll'],
                        selected_step=trial['selected_step'],train_cpu_seconds=trial['train_cpu_seconds'],
                        summary=summarize(rows),
                        by_split={s:summarize([r for r in rows if r['split']==s]) for s in splits},
                        by_task={t:summarize([r for r in rows if r['task']==t]) for t in sorted({r['task'] for r in rows})},
                        by_language={lang:summarize([r for r in rows if r['language']==lang]) for lang in ('en','pt')})
            runs.append(result)
            one=baseline_one(baseline,seed)
            pairs.append(dict(seed=seed,one_correct=one['summary']['correct'],two_correct=result['summary']['correct'],
                              correct_delta=result['summary']['correct']-one['summary']['correct'],
                              one_exact=one['summary']['exact'],two_exact=result['summary']['exact'],
                              exact_delta=result['summary']['exact']-one['summary']['exact'],
                              one_latency=one['summary']['median_internal_seconds'],
                              two_latency=result['summary']['median_internal_seconds'],
                              latency_ratio=result['summary']['median_internal_seconds']/one['summary']['median_internal_seconds'],
                              one_train_cpu_seconds=trial['baseline_one_train_cpu_seconds'],
                              two_train_cpu_seconds=trial['train_cpu_seconds'],
                              train_cpu_ratio=trial['train_cpu_seconds']/trial['baseline_one_train_cpu_seconds']))
            print(json.dumps(dict(seed=seed,summary=result['summary'])),flush=True)
    one_total=sum(p['one_correct'] for p in pairs);two_total=sum(p['two_correct'] for p in pairs)
    report=dict(protocol='native greedy generation after equal optimizer-update exposure',
                training_report_sha256=sha(training_path.read_bytes()),
                baseline_evaluation_sha256=sha(baseline_eval_path.read_bytes()),
                dataset_sha256=dataset_digest,completed=len(runs),runs=runs,pairs=pairs,
                one_correct=one_total,two_correct=two_total,correct_delta=two_total-one_total,
                two_wins=sum(p['correct_delta']>0 for p in pairs),one_wins=sum(p['correct_delta']<0 for p in pairs),
                ties=sum(p['correct_delta']==0 for p in pairs),
                median_train_cpu_ratio=statistics.median(p['train_cpu_ratio'] for p in pairs),
                median_latency_ratio=statistics.median(p['latency_ratio'] for p in pairs),
                examples=examples,energy_joules=None,
                caveats=['synthetic diagnostic tasks, not a general-assistant benchmark',
                         'one-block results are frozen from the prior native evaluation; two-block models receive the exact one-block minibatch stream and optimizer-update count'])
    out_path=Path(out_path);out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,default=ROOT/'build')
    p.add_argument('--training',type=Path,default=ROOT/'results/v012_equal_steps/training.json')
    p.add_argument('--baseline-eval',type=Path,default=ROOT/'results/v012/evaluation.json')
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    p.add_argument('--out',type=Path,default=ROOT/'results/v012_equal_steps/evaluation.json');a=p.parse_args()
    r=evaluate(a.build,a.training,a.baseline_eval,a.data,a.out)
    print(json.dumps(dict(completed=r['completed'],one_correct=r['one_correct'],two_correct=r['two_correct'],out=str(a.out))))

if __name__=='__main__': main()
