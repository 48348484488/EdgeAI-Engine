#!/usr/bin/env python3
"""Native evaluation for the v0.12 one-block vs two-block experiment."""
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
    count=len(rows)
    return dict(
        count=count,
        exact=sum(bool(r['exact']) for r in rows),
        correct=sum(bool(r['correct']) for r in rows),
        eos=sum(bool(r['stopped_on_eos']) for r in rows),
        correct_and_eos=sum(bool(r['correct']) and bool(r['stopped_on_eos']) for r in rows),
        median_generated_tokens=statistics.median(r['generated_tokens'] for r in rows) if count else None,
        median_internal_seconds=statistics.median(r['total_seconds'] for r in rows) if count else None,
        median_external_wall_seconds=statistics.median(r['external_wall_seconds'] for r in rows) if count else None,
    )


def validate_training_report(report):
    expected=report.get('expected')
    completed=report.get('completed')
    runs=report.get('runs')
    if not isinstance(expected,int) or expected<1 or completed!=expected or not isinstance(runs,list) or len(runs)!=expected:
        raise ValueError('training report incomplete')
    if set(report.get('architectures',[]))!={1,2}:
        raise ValueError('training report is not a 1x2 block comparison')
    if report.get('fairness_verified') is not True:
        raise ValueError('training fairness was not verified')
    seen=set()
    for row in runs:
        key=(row.get('seed'),row.get('blocks'))
        if key in seen or row.get('blocks') not in (1,2):
            raise ValueError('invalid or duplicate training run')
        seen.add(key)
        if not row.get('after_path') or row.get('after_path') not in row.get('artifacts',{}):
            raise ValueError('selected model artifact missing from report')
    return True


def evaluate(build,training_path,data_dir,out_path):
    build=Path(build).resolve()
    binary=build/'edgeai_generate'
    if not binary.is_file():
        raise FileNotFoundError('missing native generator: '+str(binary))
    training_path=Path(training_path)
    training=json.loads(training_path.read_text(encoding='utf-8'))
    validate_training_report(training)
    data,_=load_dataset(Path(data_dir))
    manifest_path=Path(data_dir)/'manifest.json'
    dataset_digest=sha(manifest_path.read_bytes())
    if dataset_digest!=training.get('dataset_sha256'):
        raise ValueError('dataset differs from training report')

    test_splits=('test_id','test_template','test_range','test_family')
    examples_out=[];runs_out=[];started=time.perf_counter()
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for trial in sorted(training['runs'],key=lambda r:(r['seed'],r['blocks'])):
            rel=trial['after_path'];model=(ROOT/rel).resolve()
            if not model.is_relative_to(ROOT) or not model.is_file():
                raise ValueError('model path outside repository or missing')
            if sha(model.read_bytes())!=trial['artifacts'][rel]:
                raise ValueError('model artifact hash mismatch')
            rows=[]
            for split in test_splits:
                for example in data[split]:
                    prompt=td/'prompt';answer=td/'answer'
                    prompt.write_bytes(example['prompt'].encode('utf-8'))
                    start=time.perf_counter()
                    proc=subprocess.run(
                        [str(binary),str(model),str(prompt),str(answer),'32'],
                        capture_output=True,text=True,timeout=20)
                    external=time.perf_counter()-start
                    if proc.returncode:
                        raise RuntimeError(proc.stderr or 'native generation failed')
                    metrics=json.loads(proc.stdout)
                    raw=answer.read_bytes()
                    row=dict(
                        example,split=split,seed=trial['seed'],blocks=trial['blocks'],
                        actual=raw.decode('utf-8',errors='replace'),actual_hex=raw.hex(),
                        exact=raw==example['answer'].encode('utf-8'),
                        correct=score(example,raw),
                        external_wall_seconds=external,
                        **metrics)
                    rows.append(row);examples_out.append(row)
            result=dict(
                seed=trial['seed'],blocks=trial['blocks'],model_path=rel,
                parameters=trial.get('parameters'),file_bytes=trial.get('file_bytes'),
                selected_validation_nll=trial.get('selected_validation_nll'),
                train_cpu_seconds=trial.get('train_cpu_seconds'),steps=trial.get('steps'),
                summary=summarize(rows),
                by_split={s:summarize([r for r in rows if r['split']==s]) for s in test_splits},
                by_task={t:summarize([r for r in rows if r['task']==t]) for t in sorted({r['task'] for r in rows})},
                by_language={lang:summarize([r for r in rows if r['language']==lang]) for lang in ('en','pt')},
            )
            runs_out.append(result)
            print(json.dumps(dict(seed=result['seed'],blocks=result['blocks'],summary=result['summary'])),flush=True)

    report=dict(
        protocol='native C++ greedy selected checkpoints; 32 generated tokens including EOS; no tools or deterministic shortcut',
        metric='exact raw bytes plus existing restricted expression correctness; exact and correctness reported separately',
        training_report_sha256=sha(training_path.read_bytes()),
        dataset_sha256=dataset_digest,
        runs=runs_out,examples=examples_out,completed=len(runs_out),
        wall_seconds=time.perf_counter()-started,energy_joules=None,
        caveats=[
            'synthetic diagnostic tasks, not a general-assistant benchmark',
            'validation selected checkpoints; test splits were evaluated only after selection',
            'timings include native generation and may include wrong or empty outputs',
        ],
    )
    out_path=Path(out_path);out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,default=ROOT/'build')
    p.add_argument('--report',type=Path,default=ROOT/'results/v012/training.json')
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    p.add_argument('--out',type=Path,default=ROOT/'results/v012/evaluation.json')
    a=p.parse_args()
    report=evaluate(a.build,a.report,a.data,a.out)
    print(json.dumps(dict(completed=report['completed'],out=str(a.out))),flush=True)


if __name__=='__main__':
    main()
