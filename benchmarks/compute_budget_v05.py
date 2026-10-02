#!/usr/bin/env python3
"""Exploratory follow-up: train two INT8 architectures for a CPU-time budget."""
import argparse
import copy
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from language_v05 import ROOT,make_model,evaluate,overall,atomic_json,state_hash
sys.path.insert(0,str(ROOT/'tools'))
import torch
from torch.nn import functional as F
from language_data import load_manifest,documents,evaluation_blocks,sample_batch,sha256
from mixed_model import export_mixed
from transformer_model import export_transformer

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cpu-seconds',type=float,default=12.);p.add_argument('--max-steps',type=int,default=5000);p.add_argument('--seeds',type=int,nargs='+',default=[11,22,33]);p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--out',type=Path,default=ROOT/'results/v05/compute_budget.json');a=p.parse_args()
    if not 0<a.cpu_seconds<=3600 or a.max_steps<1 or len(set(a.seeds))!=len(a.seeds):p.error('invalid budget/steps/seeds')
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    manifest=load_manifest(ROOT/'data/project_corpus');train=documents(ROOT/'data/project_corpus',manifest,'train');valid,_=evaluation_blocks(ROOT/'data/project_corpus',manifest,'valid',64);test,_=evaluation_blocks(ROOT/'data/project_corpus',manifest,'test',64)
    modeldir=ROOT/'models/compute_v05';modeldir.mkdir(parents=True,exist_ok=True);runs=[]
    # Initialize operator/thread pools outside measured training budgets.
    warm=make_model('hybrid_int8');F.cross_entropy(warm(torch.zeros(2,8,dtype=torch.long)).flatten(0,1),torch.zeros(16,dtype=torch.long)).backward();del warm
    for seed in a.seeds:
        kinds=['hybrid_int8','transformer_int8'];random.Random(seed+621).shuffle(kinds)
        for kind in kinds:
            torch.manual_seed(seed);m=make_model(kind);initial=state_hash(m);optimizer=torch.optim.AdamW(m.parameters(),lr=.002,weight_decay=.01);generator=torch.Generator().manual_seed(49100+seed)
            train_cpu=train_wall=0.;best=float('inf');best_state=None;best_step=0;curve=[];digest=hashlib.sha256();whole=time.perf_counter()
            for step in range(1,a.max_steps+1):
                m.train();c=time.process_time();w=time.perf_counter();x,y=sample_batch(train,8,64,generator);digest.update(x.numpy().tobytes());digest.update(y.numpy().tobytes())
                loss=F.cross_entropy(m(x).flatten(0,1),y.flatten())
                if not torch.isfinite(loss):raise RuntimeError('nonfinite loss')
                optimizer.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(m.parameters(),1.);optimizer.step();train_cpu+=time.process_time()-c;train_wall+=time.perf_counter()-w
                done=train_cpu>=a.cpu_seconds or step==a.max_steps
                if step%100==0 or done:
                    m.eval();metrics={d:evaluate(m,b) for d,b in valid.items()};score=overall(metrics)['bits_per_byte']
                    if score<best:best=score;best_state=copy.deepcopy(m.state_dict());best_step=step
                    curve.append(dict(step=step,train_cpu_seconds=train_cpu,validation_bpb=score))
                if done:break
            m.load_state_dict(best_state);m.eval();metrics={d:evaluate(m,b) for d,b in test.items()};edge=modeldir/f'{kind}-seed{seed}.edge';ck=edge.with_suffix('.pt')
            (export_transformer if kind.startswith('transformer') else export_mixed)(m,edge)
            torch.save(dict(kind=kind,config=m.export_config(),state_dict=best_state,selected_step=best_step,dataset_id=manifest['dataset_id']),ck)
            native_metrics={}
            for domain in test:
                native=json.loads(subprocess.check_output([str((a.build/'edgeai_evaluate').resolve()),str(edge),str(ROOT/f'data/project_corpus/test_{domain}.blocks')],text=True));ref=metrics[domain]
                if abs(native['bits_per_byte']-ref['bits_per_byte'])>3e-5 or native['correct']!=ref['correct']:raise AssertionError('budget model native mismatch')
                native_metrics[domain]=native
            row=dict(kind=kind,seed=seed,steps=step,training_tokens=step*8*64,train_cpu_seconds=train_cpu,train_seconds=train_wall,trial_seconds=time.perf_counter()-whole,selected_step=best_step,selected_validation_bpb=best,initial_state_sha256=initial,training_batches_sha256=digest.hexdigest(),metrics=metrics,overall=overall(metrics),native_metrics=native_metrics,curve=curve,model_path=str(edge.relative_to(ROOT)),artifacts={str(f.relative_to(ROOT)):sha256(f.read_bytes()) for f in (edge,ck)})
            runs.append(row);print(json.dumps({k:row[k] for k in ('kind','seed','steps','train_cpu_seconds','selected_step','overall')}),flush=True)
            atomic_json(a.out,dict(protocol='follow-up after fixed-update comparison; CPU process time budget excluding evaluation/export, no identical FLOPs/data-exposure/energy claim',cpu_budget=a.cpu_seconds,max_steps=a.max_steps,seeds=a.seeds,dataset_id=manifest['dataset_id'],completed=len(runs),expected=len(a.seeds)*2,runs=runs))
if __name__=='__main__':main()
