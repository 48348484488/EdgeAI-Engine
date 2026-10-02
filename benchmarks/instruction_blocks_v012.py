#!/usr/bin/env python3
"""Controlled v0.12 one-block vs two-block instruction experiment.

The experiment keeps all declared controls identical and permits only the
Transformer block count to differ inside a paired comparison. Validation
selects checkpoints; test splits are never read here.
"""
import argparse
import copy
import hashlib
import json
import os
import platform
import random
import sys
import time
from pathlib import Path

import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss
from transformer_model import TinyTransformer,export_transformer,numeric_weight_bytes

SEEDS=(11,22,33)
ARCHITECTURES=(1,2)
DEFAULT_THREADS=1
DEFAULT_CPU_SECONDS=60.0

_CONTROL_KEYS=(
    'protocol','seed','cpu_budget','threads','dataset_sha256',
    'tokenizer_fingerprint','dim','hidden','window','precision',
    'batch','lr','weight_decay','clip_norm','max_length','selection',
)


def assert_fair_pair(one,two):
    """Reject a 1x2 comparison if anything controlled differs."""
    if one.get('blocks')!=1 or two.get('blocks')!=2:
        raise ValueError('paired architectures must be blocks=1 and blocks=2')
    missing=[key for key in _CONTROL_KEYS if key not in one or key not in two]
    if missing:
        raise ValueError('missing controlled identity fields: '+','.join(missing))
    changed=[key for key in _CONTROL_KEYS if one[key]!=two[key]]
    if changed:
        raise ValueError('unfair paired comparison: '+','.join(changed))
    return True


def promote_blocks(base,blocks,seed):
    """Return an independent N-block model while preserving the trained base path."""
    if not isinstance(base,TinyTransformer) or len(base.blocks)!=1:
        raise ValueError('promotion requires a one-block TinyTransformer base')
    if not 1<=blocks<=8:
        raise ValueError('blocks must be in [1,8]')
    if blocks==1:
        return copy.deepcopy(base)
    config=base.export_config()
    config['blocks']=blocks
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(int(seed)+12000)
        promoted=TinyTransformer(**config)
    promoted.emb.load_state_dict(base.emb.state_dict())
    promoted.out.load_state_dict(base.out.state_dict())
    promoted.blocks[0].load_state_dict(base.blocks[0].state_dict())
    promoted.train(base.training)
    return promoted


def build_identity(seed,blocks,cpu_budget,threads,dataset_sha256,tokenizer_fingerprint,config):
    """Build the immutable comparison identity used by both architectures."""
    if blocks not in ARCHITECTURES:
        raise ValueError('v0.12 experiment supports blocks=1 or blocks=2')
    required=('dim','hidden','window','precision')
    if any(key not in config for key in required):
        raise ValueError('incomplete Transformer config')
    return dict(
        protocol='edge-sft-v012-blocks-1',
        seed=int(seed),
        cpu_budget=float(cpu_budget),
        threads=int(threads),
        dataset_sha256=str(dataset_sha256),
        tokenizer_fingerprint=str(tokenizer_fingerprint),
        dim=int(config['dim']),
        hidden=int(config['hidden']),
        window=int(config['window']),
        precision=str(config['precision']),
        vocab_size=int(config['vocab_size']) if 'vocab_size' in config else None,
        batch=16,
        lr=.001,
        weight_decay=.01,
        clip_norm=1.0,
        max_length=128,
        selection='minimum response validation NLL at 25/50/75/100 percent',
        blocks=int(blocks),
    )


def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    os.replace(tmp,path)


def cached_ok(row,identity):
    if row.get('identity')!=identity:
        return False
    artifacts=row.get('artifacts',{})
    if len(artifacts)!=4:
        return False
    for rel,digest in artifacts.items():
        path=(ROOT/rel).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or sha(path.read_bytes())!=digest:
            return False
    return True


def train_trial(seed,blocks,cpu_seconds,threads,data,groups,dataset_digest,model_dir,base_path):
    trial_wall=time.perf_counter();trial_cpu=time.process_time();init=time.perf_counter()
    checkpoint=torch.load(base_path,map_location='cpu',weights_only=True)
    base_model,tok=expand_checkpoint(checkpoint,seed)
    model=promote_blocks(base_model,blocks,seed)
    identity=build_identity(
        seed,blocks,cpu_seconds,threads,dataset_digest,tok.fingerprint(),model.export_config())
    train=data['train'];valid=data['valid']

    for rows in (train,valid):
        for i in range(0,len(rows),16):
            make_batch(rows[i:i+16],tok)

    stem=f'seed{seed}-b{blocks}'
    before=model_dir/(stem+'-before.edge')
    after=model_dir/(stem+'-after.edge')
    export_transformer(model,before,tokenizer=tok,max_generate=32)
    torch.save(dict(
        config=model.export_config(),state_dict=model.state_dict(),tokenizer=tok.payload(),
        seed=seed,blocks=blocks,phase='before',identity=identity),
        before.with_suffix('.pt'))

    optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    init_wall=time.perf_counter()-init
    baseline_valid=validation_loss(model,valid,tok)
    rng=random.Random(7700+seed)
    tasks=sorted(groups)
    cpu=wall=0.0;step=0;threshold=1
    best=float('inf');best_state=None;best_step=0;curve=[]
    seen={task:0 for task in tasks};digest=hashlib.sha256();validation_cpu=0.0

    while cpu<cpu_seconds and step<100000:
        model.train();start_cpu=time.process_time();start_wall=time.perf_counter()
        batch=[]
        for _ in range(16):
            task=rng.choice(tasks);row=rng.choice(groups[task])
            batch.append(row);seen[task]+=1;digest.update(row['id'].encode())
        x,y=make_batch(batch,tok)
        optimizer.zero_grad(set_to_none=True)
        loss=response_loss(model(x),y)
        if not torch.isfinite(loss):
            raise RuntimeError('nonfinite training loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        cpu+=time.process_time()-start_cpu;wall+=time.perf_counter()-start_wall;step+=1
        if cpu>=cpu_seconds*threshold/4 or cpu>=cpu_seconds:
            start_validation=time.process_time()
            metric=validation_loss(model,valid,tok)
            curve.append(dict(step=step,train_cpu_seconds=cpu,validation_nll=metric))
            if metric<best:
                best=metric;best_state=copy.deepcopy(model.state_dict());best_step=step
            validation_cpu+=time.process_time()-start_validation
            threshold+=1
            print(json.dumps(dict(seed=seed,blocks=blocks,step=step,
                                  train_cpu_seconds=cpu,validation_nll=metric)),flush=True)

    if best_state is None:
        raise RuntimeError('no validation checkpoint')
    model.load_state_dict(best_state);model.eval()
    export_transformer(model,after,tokenizer=tok,max_generate=32)
    torch.save(dict(
        config=model.export_config(),state_dict=best_state,tokenizer=tok.payload(),
        seed=seed,blocks=blocks,phase='after',identity=identity,selected_step=best_step),
        after.with_suffix('.pt'))
    artifact_paths=(before,before.with_suffix('.pt'),after,after.with_suffix('.pt'))
    artifacts={str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in artifact_paths}
    return dict(
        seed=seed,blocks=blocks,identity=identity,
        source_checkpoint_sha256=sha(base_path.read_bytes()),
        parameters=sum(p.numel() for p in model.parameters()),
        steps=step,selected_step=best_step,train_cpu_seconds=cpu,train_wall_seconds=wall,
        initialization_wall_seconds=init_wall,validation_cpu_seconds=validation_cpu,
        total_trial_wall_seconds=time.perf_counter()-trial_wall,
        total_trial_cpu_seconds=time.process_time()-trial_cpu,
        before_validation_nll=baseline_valid,selected_validation_nll=best,
        validation_curve=curve,examples_seen=seen,batch_ids_sha256=digest.hexdigest(),
        before_path=str(before.relative_to(ROOT)),after_path=str(after.relative_to(ROOT)),
        file_bytes=after.stat().st_size,
        numeric_weight_bytes=numeric_weight_bytes(model),
        cache_payload_bytes=8*blocks*model.window*model.dim,
        artifacts=artifacts,
    )


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-seconds',type=float,default=DEFAULT_CPU_SECONDS)
    parser.add_argument('--seeds',type=int,nargs='+',default=list(SEEDS))
    parser.add_argument('--threads',type=int,default=DEFAULT_THREADS)
    parser.add_argument('--architectures',type=int,nargs='+',default=list(ARCHITECTURES))
    parser.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    parser.add_argument('--out',type=Path,default=ROOT/'results/v012/training.json')
    parser.add_argument('--model-dir',type=Path,default=ROOT/'models/v012')
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if not 0<args.cpu_seconds<=3600:
        parser.error('cpu budget must be in (0,3600]')
    if not 1<=args.threads<=64 or not args.seeds or len(set(args.seeds))!=len(args.seeds):
        parser.error('invalid threads/seeds')
    if not args.architectures or len(set(args.architectures))!=len(args.architectures) or any(b not in ARCHITECTURES for b in args.architectures):
        parser.error('architectures must be unique values from 1,2')

    torch.set_num_threads(args.threads);torch.use_deterministic_algorithms(True)
    data,_=load_dataset(args.data)
    train=data['train'];groups={}
    for row in train:
        groups.setdefault(row['task'],[]).append(row)
    args.model_dir.mkdir(parents=True,exist_ok=True)
    dataset_digest=sha((args.data/'manifest.json').read_bytes())

    old={}
    if args.resume and args.out.exists():
        for row in json.loads(args.out.read_text(encoding='utf-8')).get('runs',[]):
            old[(row.get('seed'),row.get('blocks'))]=row

    report=dict(
        protocol='same frozen instruction data and process-CPU budget; only block count differs',
        cpu_budget_seconds=args.cpu_seconds,seeds=args.seeds,architectures=args.architectures,
        threads=args.threads,expected=len(args.seeds)*len(args.architectures),
        dataset_sha256=dataset_digest,runs=[],
        accounting='training CPU includes batch creation, sampling, forward/backward, optimizer and batch hashing; initialization, validation, saving and inference excluded and reported separately',
        synthetic=True,energy_joules=None,torch=str(torch.__version__),
        platform=platform.platform(),python=sys.version,
    )
    invocation=time.perf_counter()
    for seed in args.seeds:
        base_path=ROOT/f'models/external_v06/bpe513-seed{seed}.pt'
        if not base_path.exists():
            raise FileNotFoundError('need v0.6 BPE checkpoint: '+str(base_path))
        pair=[]
        for blocks in args.architectures:
            checkpoint=torch.load(base_path,map_location='cpu',weights_only=True)
            base_model,tok=expand_checkpoint(checkpoint,seed)
            candidate=promote_blocks(base_model,blocks,seed)
            identity=build_identity(seed,blocks,args.cpu_seconds,args.threads,dataset_digest,
                                    tok.fingerprint(),candidate.export_config())
            key=(seed,blocks)
            if key in old and cached_ok(old[key],identity):
                row=old[key];print(f'seed {seed} blocks {blocks}: verified cached trial',flush=True)
            else:
                row=train_trial(seed,blocks,args.cpu_seconds,args.threads,data,groups,
                                dataset_digest,args.model_dir,base_path)
            report['runs'].append(row);pair.append(row);report['completed']=len(report['runs']);save(args.out,report)
        if set(args.architectures)==set(ARCHITECTURES):
            by_blocks={row['blocks']:row for row in pair}
            assert_fair_pair(by_blocks[1]['identity'],by_blocks[2]['identity'])

    report['completed']=len(report['runs'])
    report['fairness_verified']=all(
        assert_fair_pair(
            next(r for r in report['runs'] if r['seed']==seed and r['blocks']==1)['identity'],
            next(r for r in report['runs'] if r['seed']==seed and r['blocks']==2)['identity'])
        for seed in args.seeds
    ) if set(args.architectures)==set(ARCHITECTURES) else None
    report['invocation_wall_seconds']=time.perf_counter()-invocation
    save(args.out,report)
    print(json.dumps(dict(completed=report['completed'],fairness_verified=report['fairness_verified'],
                          out=str(args.out))),flush=True)


if __name__=='__main__':
    main()
