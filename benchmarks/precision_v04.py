#!/usr/bin/env python3
"""Predeclared synthetic recall benchmark. Not a general-language benchmark.

Six hybrid precision policies have identical FP32 master initialization per seed,
same examples, optimizer and update count. Transformer uses a near-matched count.
No checkpoint/seed selection on test; every final checkpoint is reported and saved.
"""
import argparse
import hashlib
import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import torch
from torch.nn import functional as F
from mixed_model import MixedHybrid, POLICIES, numeric_weight_bytes, export_mixed
from quality_v03 import Transformer, batch

def evaluate(model, batches):
    correct=total=0; nll=0.
    with torch.inference_mode():
        for x,y in batches:
            logits=model(x)[:,-1]
            correct+=int((logits.argmax(-1)==y).sum())
            total+=len(y);nll+=float(F.cross_entropy(logits,y,reduction='sum'))
    return dict(accuracy=correct/total,correct=correct,total=total,nll=nll/total)

def data_hash(batches):
    h=hashlib.sha256()
    for x,y in batches:h.update(x.numpy().tobytes());h.update(y.numpy().tobytes())
    return h.hexdigest()

def state_hash(model):
    h=hashlib.sha256()
    for name,p in model.state_dict().items():h.update(name.encode());h.update(p.numpy().tobytes())
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--steps',type=int,default=400)
    p.add_argument('--seeds',type=int,nargs='+',default=[11,22,33])
    p.add_argument('--test-size',type=int,default=1024)
    p.add_argument('--threads',type=int,default=1)
    p.add_argument('--out',type=Path,default=Path('results/precision_quality.json'))
    p.add_argument('--checkpoint-dir',type=Path,default=Path('models/recall'))
    args=p.parse_args()
    if min(args.steps,args.threads,args.test_size)<1 or args.test_size%32:
        p.error('positive steps/threads/test-size; test-size must be a multiple of 32')
    if len(set(args.seeds))!=len(args.seeds):p.error('seeds must not repeat')
    torch.set_num_threads(args.threads);torch.use_deterministic_algorithms(True)
    tests={}
    for length in (32,64):
        generator=torch.Generator().manual_seed(268113+length)
        tests[str(length)]=[batch(32,length,generator) for _ in range(args.test_size//32)]
    args.checkpoint_dir.mkdir(parents=True,exist_ok=True)
    rows=[];kinds=list(POLICIES)+['transformer_fp32'];initial_hashes={}
    for seed in args.seeds:
        order=list(kinds);random.Random(seed+802).shuffle(order)
        for kind in order:
            torch.manual_seed(seed)
            model=Transformer(hidden=16) if kind=='transformer_fp32' else MixedHybrid(policy=kind)
            initial=state_hash(model)
            if kind!='transformer_fp32':
                previous=initial_hashes.setdefault(seed,initial)
                if initial!=previous:raise AssertionError('hybrid master initialization mismatch')
            optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.01)
            generator=torch.Generator().manual_seed(8100+seed)
            batch_digest=hashlib.sha256();curve=[]
            model.train();start=time.perf_counter();cpu_start=time.process_time()
            for step in range(1,args.steps+1):
                x,y=batch(32,32,generator)
                batch_digest.update(x.numpy().tobytes());batch_digest.update(y.numpy().tobytes())
                loss=F.cross_entropy(model(x)[:,-1],y)
                if not torch.isfinite(loss):raise RuntimeError(f'nonfinite loss: {kind}/{seed}/{step}')
                optimizer.zero_grad(set_to_none=True);loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
                if step%100==0 or step==args.steps:curve.append(dict(step=step,loss=float(loss.detach())))
            cpu=time.process_time()-cpu_start;elapsed=time.perf_counter()-start
            model.eval();metrics={length:evaluate(model,test) for length,test in tests.items()}
            config={} if kind=='transformer_fp32' else model.export_config()
            checkpoint=args.checkpoint_dir/f'{kind}-seed{seed}.pt'
            torch.save(dict(kind=kind,seed=seed,steps=args.steps,config=config,state_dict=model.state_dict()),checkpoint)
            export_bytes=None;payload_bytes=sum(p.numel() for p in model.parameters())*4
            if kind!='transformer_fp32':
                export_mixed(model,checkpoint.with_suffix('.edge'))
                export_bytes=checkpoint.with_suffix('.edge').stat().st_size
                payload_bytes=numeric_weight_bytes(model)
            row=dict(kind=kind,seed=seed,parameters=sum(p.numel() for p in model.parameters()),
                     initial_state_sha256=initial,training_batches_sha256=batch_digest.hexdigest(),
                     steps=args.steps,train_examples=args.steps*32,train_seconds=elapsed,
                     train_cpu_seconds=cpu,energy_joules=None,metrics=metrics,
                     numeric_weight_bytes=payload_bytes,edge_file_bytes=export_bytes,curve=curve,
                     checkpoint=str(checkpoint))
            rows.append(row);print(json.dumps(row),flush=True)
    for seed in args.seeds:
        if len({r['training_batches_sha256'] for r in rows if r['seed']==seed})!=1:
            raise AssertionError('training batches differ across variants')
    summary={}
    for kind in kinds:
        group=[r for r in rows if r['kind']==kind]
        summary[kind]=dict(parameters=group[0]['parameters'],numeric_weight_bytes=group[0]['numeric_weight_bytes'],
                          edge_file_bytes=group[0]['edge_file_bytes'],mean_train_seconds=statistics.mean(r['train_seconds'] for r in group),
                          mean_train_cpu_seconds=statistics.mean(r['train_cpu_seconds'] for r in group),
                          by_length={length:dict(mean_accuracy=statistics.mean(r['metrics'][length]['accuracy'] for r in group),
                             min_accuracy=min(r['metrics'][length]['accuracy'] for r in group),
                             max_accuracy=max(r['metrics'][length]['accuracy'] for r in group)) for length in tests})
    report=dict(task='6 joint key/value symbols followed by distractors and a query; 8 values; chance 12.5%',
                limitations='Synthetic task; not natural language, code or general intelligence. Three seeds are not an inferential confidence interval.',
                policy_definitions=POLICIES,primary_length=32,stress_length=64,local_window=16,
                steps=args.steps,batch_size=32,seeds=args.seeds,test_size=args.test_size,
                test_seed_by_length={length:268113+int(length) for length in tests},
                test_sha256={length:data_hash(test) for length,test in tests.items()},
                checkpoint_selection='final fixed step for every run; no test selection',
                optimizer='AdamW lr=.002 weight_decay=.01 clip_norm=1',
                precision_note='FP32 master weights/gradients/state. Ternary uses per-row centering; INT8 uses absmax scale without centering. Comparisons include this policy difference.',
                transformer_note='Transformer hidden=16, hybrid hidden=64 to near-match total parameters; neither FLOPs nor architecture equalized.',
                torch_version=torch.__version__,threads=args.threads,platform=platform.platform(),
                summary=summary,runs=rows)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':main()
