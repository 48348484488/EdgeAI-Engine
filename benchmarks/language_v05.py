#!/usr/bin/env python3
"""Controlled byte prediction on frozen real project source/docs, NOT chat quality.

Resumes completed trials only after checking code/data/config and output hashes.
No test-based model selection. All fresh test outcomes are saved, not only winners.
"""
import argparse
import copy
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import torch
from torch.nn import functional as F
from mixed_model import MixedHybrid,export_mixed,numeric_weight_bytes as hybrid_bytes
from transformer_model import TinyTransformer,export_transformer,numeric_weight_bytes as transformer_bytes
from language_data import load_manifest,documents,evaluation_blocks,sample_batch,bits_per_byte,write_blocks,sha256
VARIANTS=('hybrid_fp32','hybrid_int8','hybrid_mixed','transformer_fp32','transformer_int8')

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');os.replace(tmp,path)

def make_model(kind):
    if kind.startswith('transformer_'):
        return TinyTransformer(dim=64,hidden=96,window=64,precision=kind.split('_',1)[1])
    policy={'hybrid_fp32':'fp32','hybrid_int8':'int8','hybrid_mixed':'memory_int8'}[kind]
    return MixedHybrid(dim=64,hidden=128,key_dim=32,window=64,loops=1,policy=policy,output_precision='fp32' if policy=='fp32' else 'int8')

def state_hash(model):
    h=hashlib.sha256()
    for n,p in model.state_dict().items():h.update(n.encode());h.update(p.detach().cpu().numpy().tobytes())
    return h.hexdigest()

def evaluate(model,blocks):
    correct=total=0;nll=0.
    with torch.inference_mode():
        # Group equal lengths to preserve every byte and avoid padding targets.
        lengths={len(x) for x,y in blocks}
        for length in sorted(lengths):
            group=[(x,y) for x,y in blocks if len(x)==length]
            for start in range(0,len(group),16):
                subset=group[start:start+16];x=torch.tensor([r[0] for r in subset]);y=torch.tensor([r[1] for r in subset]);z=model(x)
                nll+=float(F.cross_entropy(z.double().flatten(0,1),y.flatten(),reduction='sum'))
                correct+=int((z.argmax(-1)==y).sum());total+=y.numel()
    return dict(targets=total,correct=correct,accuracy=correct/total,nll_sum=nll,bits_per_byte=bits_per_byte(nll,total))

def overall(domain_metrics):
    nll=sum(v['nll_sum'] for v in domain_metrics.values());count=sum(v['targets'] for v in domain_metrics.values());correct=sum(v['correct'] for v in domain_metrics.values())
    return dict(nll_sum=nll,targets=count,correct=correct,bits_per_byte=bits_per_byte(nll,count),accuracy=correct/count)

def bigram(train,tests):
    counts=torch.full((256,256),.1,dtype=torch.float64)
    for d in train:
        x=torch.tensor(list(d[:-1]));y=torch.tensor(list(d[1:]));flat=torch.bincount(x*256+y,minlength=65536).reshape(256,256);counts+=flat
    logp=(counts/counts.sum(1,keepdim=True)).log();pred=logp.argmax(-1);metrics={}
    for domain,blocks in tests.items():
        nll=0.;correct=total=0
        for x,y in blocks:
            a,b=torch.tensor(x),torch.tensor(y);nll-=float(logp[a,b].sum());correct+=int((pred[a]==b).sum());total+=len(y)
        metrics[domain]=dict(nll_sum=nll,targets=total,correct=correct,bits_per_byte=bits_per_byte(nll,total),accuracy=correct/total)
    return dict(smoothing=.1,training='counts over train split only',metrics=metrics,overall=overall(metrics))

def code_fingerprint():
    paths=[Path(__file__),ROOT/'tools/hybrid_model.py',ROOT/'tools/mixed_model.py',ROOT/'tools/transformer_model.py',ROOT/'tools/language_data.py',ROOT/'tools/train_tiny.py']
    return sha256(b''.join(p.read_bytes() for p in paths))

def trial_signature(config):return sha256(json.dumps(config,sort_keys=True).encode())
def reusable(row,signature):
    if row.get('signature')!=signature:return False
    for path,digest in row.get('artifacts',{}).items():
        p=ROOT/path
        if not p.is_file() or sha256(p.read_bytes())!=digest:return False
    return bool(row.get('artifacts'))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus',type=Path,default=ROOT/'data/project_corpus');p.add_argument('--steps',type=int,default=400)
    p.add_argument('--seeds',type=int,nargs='+',default=[11,22,33]);p.add_argument('--variants',nargs='+',choices=VARIANTS,default=list(VARIANTS));p.add_argument('--threads',type=int,default=1)
    p.add_argument('--model-dir',type=Path,default=ROOT/'models/language_v05');p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--out',type=Path,default=ROOT/'results/v05/language.json');p.add_argument('--resume',action='store_true')
    a=p.parse_args()
    if not 1<=a.steps<=100000 or not 1<=a.threads<=256 or len(set(a.seeds))!=len(a.seeds) or len(set(a.variants))!=len(a.variants):p.error('invalid/duplicate run parameters')
    torch.set_num_threads(a.threads);torch.use_deterministic_algorithms(True)
    manifest=load_manifest(a.corpus);train=documents(a.corpus,manifest,'train')
    valid,vstats=evaluation_blocks(a.corpus,manifest,'valid',64);tests,tstats=evaluation_blocks(a.corpus,manifest,'test',64)
    for split,blocks in (('valid',valid),('test',tests)):
        for domain,b in blocks.items():write_blocks(b,a.corpus/f'{split}_{domain}.blocks')
    source_hash=code_fingerprint();native=(a.build/'edgeai_evaluate').resolve()
    if not native.is_file():raise FileNotFoundError('build edgeai_evaluate before training')
    base_config=dict(dataset_id=manifest['dataset_id'],code_sha256=source_hash,steps=a.steps,batch_size=8,sequence=64,lr=.002,weight_decay=.01,clip_norm=1,threads=a.threads,torch_version=str(torch.__version__),validation_every=100,native_sha256=sha256(native.read_bytes()))
    rows=[];outdir=a.out.parent;outdir.mkdir(parents=True,exist_ok=True);modeldir=a.model_dir.resolve();
    if not modeldir.is_relative_to(ROOT):raise ValueError('model-dir must be inside the project')
    modeldir.mkdir(parents=True,exist_ok=True)
    bg=bigram(train,tests)
    for seed in a.seeds:
        kinds=list(a.variants);random.Random(seed+923).shuffle(kinds)
        for kind in kinds:
            config=dict(base_config,kind=kind,seed=seed);signature=trial_signature(config)
            rowfile=outdir/f'{kind}-seed{seed}.json'
            if a.resume and rowfile.exists():
                row=json.loads(rowfile.read_text())
                if reusable(row,signature):rows.append(row);print(f'reused verified {kind} seed={seed}',flush=True);continue
            torch.manual_seed(seed);model=make_model(kind);initial=state_hash(model)
            optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.01)
            generator=torch.Generator().manual_seed(49100+seed);digest=hashlib.sha256()
            best_state=None;best_valid=float('inf');best_step=0;curve=[];train_seconds=train_cpu=0.
            validation_seconds=0.;whole_start=time.perf_counter();loss_first=None
            for step in range(1,a.steps+1):
                model.train();start=time.perf_counter();cpu=time.process_time()
                x,y=sample_batch(train,8,64,generator);digest.update(x.numpy().tobytes());digest.update(y.numpy().tobytes())
                loss=F.cross_entropy(model(x).flatten(0,1),y.flatten())
                if not torch.isfinite(loss):raise RuntimeError(f'nonfinite training loss {kind} {seed} {step}')
                optimizer.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
                train_cpu+=time.process_time()-cpu;train_seconds+=time.perf_counter()-start
                if step==1:loss_first=float(loss.detach())
                if step%100==0 or step==a.steps:
                    model.eval();start=time.perf_counter();vm={d:evaluate(model,b) for d,b in valid.items()};score=overall(vm)['bits_per_byte'];validation_seconds+=time.perf_counter()-start
                    if score<best_valid:best_valid=score;best_step=step;best_state=copy.deepcopy(model.state_dict())
                    curve.append(dict(step=step,training_nll=float(loss.detach()),validation_bpb=score))
                    print(f'{kind} seed={seed} step={step}/{a.steps} validation_bpb={score:.4f}',flush=True)
            model.load_state_dict(best_state);model.eval()
            metrics={d:evaluate(model,b) for d,b in tests.items()}
            ck=modeldir/f'{kind}-seed{seed}.pt';edge=ck.with_suffix('.edge')
            state=dict(kind=kind,config=model.export_config(),state_dict=best_state,training_config=config,selected_step=best_step,dataset_id=manifest['dataset_id'])
            tmp=ck.with_suffix('.pt.tmp');torch.save(state,tmp);os.replace(tmp,ck)
            (export_transformer if kind.startswith('transformer_') else export_mixed)(model,edge)
            native_metrics={}
            for domain in tests:
                output=subprocess.check_output([str(native),str(edge),str(a.corpus/f'test_{domain}.blocks')],text=True)
                nm=json.loads(output);pm=metrics[domain]
                if nm['targets']!=pm['targets'] or nm['correct']!=pm['correct'] or abs(nm['bits_per_byte']-pm['bits_per_byte'])>3e-5:raise AssertionError(f'native metrics mismatch {kind} {seed} {domain}: {nm} {pm}')
                native_metrics[domain]=nm
            params=sum(p.numel() for p in model.parameters());payload=(transformer_bytes if kind.startswith('transformer_') else hybrid_bytes)(model)
            row=dict(signature=signature,kind=kind,seed=seed,parameters=params,initial_state_sha256=initial,training_batches_sha256=digest.hexdigest(),training_tokens=a.steps*8*64,steps=a.steps,selected_step=best_step,selected_validation_bpb=best_valid,first_training_nll=loss_first,train_seconds=train_seconds,train_cpu_seconds=train_cpu,validation_seconds=validation_seconds,trial_seconds=time.perf_counter()-whole_start,metrics=metrics,overall=overall(metrics),native_metrics=native_metrics,curve=curve,numeric_weight_bytes=payload,edge_file_bytes=edge.stat().st_size,energy_joules=None,model_path=str(edge.relative_to(ROOT)),artifacts={str(f.relative_to(ROOT)):sha256(f.read_bytes()) for f in (ck,edge)})
            atomic_json(rowfile,row);rows.append(row)
    for seed in a.seeds:
        group=[r for r in rows if r['seed']==seed]
        if len({r['training_batches_sha256'] for r in group})!=1:raise AssertionError('training data differs across variants')
        for arch in ('hybrid_','transformer_'):
            if len({r['initial_state_sha256'] for r in group if r['kind'].startswith(arch)})>1:raise AssertionError('initial masters differ within architecture')
    summary={}
    for kind in a.variants:
        group=[r for r in rows if r['kind']==kind]
        summary[kind]=dict(parameters=group[0]['parameters'],edge_file_bytes=group[0]['edge_file_bytes'],numeric_weight_bytes=group[0]['numeric_weight_bytes'],mean_training_seconds=statistics.mean(r['train_seconds'] for r in group),mean_bpb=statistics.mean(r['overall']['bits_per_byte'] for r in group),min_bpb=min(r['overall']['bits_per_byte'] for r in group),max_bpb=max(r['overall']['bits_per_byte'] for r in group),mean_accuracy=statistics.mean(r['overall']['accuracy'] for r in group),by_domain={d:dict(mean_bpb=statistics.mean(r['metrics'][d]['bits_per_byte'] for r in group),mean_accuracy=statistics.mean(r['metrics'][d]['accuracy'] for r in group)) for d in tests})
    report=dict(task='next UTF-8/raw byte in frozen EdgeAI v0.4 source/docs; NOT instruction following or Claude comparison',protocol=base_config,seeds=a.seeds,platform=platform.platform(),corpus_stats={s:{d:sum(map(len,documents(a.corpus,manifest,s,d))) for d in ('code','text')} for s in ('train','valid','test')},validation_blocks=vstats,test_blocks=tstats,selection='lowest validation bpb at every 100 steps/final; test evaluated after training only',bigram=bg,summary=summary,runs=rows,limitations=['Predominantly generated project source/docs, narrow corpus; not general language benchmark.','Grouped by file family and exact-block overlap removed; near duplicates/identifiers may remain.','All models single-block microscale; 3 seeds are not a confidence interval.','QAT uses FP32 masters, gradients and state; INT8 weights do not imply INT8 training.','No GPU or energy sensor; wall time does not imply joules.'])
    atomic_json(a.out,report);print(json.dumps(summary,indent=2),flush=True)
if __name__=='__main__':main()
