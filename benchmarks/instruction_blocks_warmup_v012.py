#!/usr/bin/env python3
"""v0.12 new-block warm-up ablation with gradient diagnostics.

The two-block model starts function-preserving: block 1's residual output
projections are zero. This ablation freezes inherited parameters for a short
phase so the new block learns a residual correction before joint fine-tuning.
"""
import argparse,copy,hashlib,json,math,random,sys,time
from pathlib import Path
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss
from transformer_model import export_transformer,numeric_weight_bytes
from instruction_blocks_v012 import promote_blocks,repo_path
from instruction_blocks_equal_steps_v012 import baseline_plan,target_steps

SEEDS=(11,22,33)
DEFAULT_THREADS=1
WARMUP_STEPS=1024
PROBE_STEPS=(1,2,4,8,16,32,64,128,256,512,1024)

def set_train_phase(model,phase):
    if len(model.blocks)!=2:
        raise ValueError('warm-up ablation requires exactly two blocks')
    if phase not in ('new_block','all'):
        raise ValueError('unknown train phase')
    for p in model.parameters():
        p.requires_grad_(phase=='all')
    if phase=='new_block':
        for p in model.blocks[1].parameters():
            p.requires_grad_(True)
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

def _norm(params,attr):
    total=0.0
    for p in params:
        x=getattr(p,attr,None)
        if x is not None:
            total+=float(x.detach().float().pow(2).sum())
    return math.sqrt(total)

def gradient_snapshot(model):
    inherited=list(model.emb.parameters())+list(model.blocks[0].parameters())+list(model.out.parameters())
    new_inner=[]
    new_output=[]
    for name in ('query','key','value','up'):
        new_inner.extend(getattr(model.blocks[1],name).parameters())
    for name in ('project','down'):
        new_output.extend(getattr(model.blocks[1],name).parameters())
    return dict(
        inherited_grad_l2=_norm(inherited,'grad'),
        new_inner_grad_l2=_norm(new_inner,'grad'),
        new_output_grad_l2=_norm(new_output,'grad'),
        new_inner_weight_l2=_norm(new_inner,'data'),
        new_output_weight_l2=_norm(new_output,'data'),
    )

def train(seed,plan,threads,data,groups,dataset_digest,model_dir,warmup_steps):
    base_path=ROOT/f'models/external_v06/bpe513-seed{seed}.pt'
    if sha(base_path.read_bytes())!=plan['source_checkpoint_sha256']:
        raise ValueError('baseline source checkpoint changed')
    cp=torch.load(base_path,map_location='cpu',weights_only=True)
    base,tok=expand_checkpoint(cp,seed);model=promote_blocks(base,2,seed)
    if warmup_steps>=plan['target_steps']:
        raise ValueError('warm-up must be shorter than target training')
    rng=random.Random(7700+seed);tasks=sorted(groups)
    optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    best=float('inf');best_state=None;best_step=0;curve=[];probes=[];digest=hashlib.sha256()
    seen={task:0 for task in tasks};marks=set(plan['validation_steps'])
    train_cpu=train_wall=0.0
    set_train_phase(model,'new_block')
    for step in range(1,plan['target_steps']+1):
        if step==warmup_steps+1:
            set_train_phase(model,'all')
        model.train();c0=time.process_time();w0=time.perf_counter();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);row=rng.choice(groups[task]);batch.append(row)
            seen[task]+=1;digest.update(row['id'].encode())
        x,y=make_batch(batch,tok);optimizer.zero_grad(set_to_none=True)
        loss=response_loss(model(x),y)
        if not torch.isfinite(loss): raise RuntimeError('nonfinite training loss')
        loss.backward()
        if step in PROBE_STEPS or step in (warmup_steps,warmup_steps+1):
            snap=gradient_snapshot(model);snap.update(step=step,phase='new_block' if step<=warmup_steps else 'all',loss=float(loss.detach()))
            probes.append(snap)
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],1.0)
        optimizer.step();train_cpu+=time.process_time()-c0;train_wall+=time.perf_counter()-w0
        if step in marks:
            metric=validation_loss(model,data['valid'],tok)
            curve.append(dict(step=step,validation_nll=metric,train_cpu_seconds=train_cpu))
            if metric<best: best=metric;best_state=copy.deepcopy(model.state_dict());best_step=step
            print(json.dumps(dict(seed=seed,step=step,validation_nll=metric,phase='new_block' if step<=warmup_steps else 'all')),flush=True)
    if digest.hexdigest()!=plan['batch_ids_sha256'] or seen!=plan['examples_seen']:
        raise RuntimeError('warm-up changed data exposure')
    if best_state is None: raise RuntimeError('no validation checkpoint')
    model.load_state_dict(best_state);model.eval();model_dir.mkdir(parents=True,exist_ok=True)
    edge=model_dir/f'seed{seed}-b2-warmup{warmup_steps}.edge'
    export_transformer(model,edge,tokenizer=tok,max_generate=32)
    rel=str(edge.relative_to(ROOT))
    return dict(seed=seed,blocks=2,warmup_steps=warmup_steps,target_steps=plan['target_steps'],steps=plan['target_steps'],
                selected_step=best_step,selected_validation_nll=best,validation_curve=curve,
                train_cpu_seconds=train_cpu,train_wall_seconds=train_wall,gradient_probes=probes,
                batch_ids_sha256=digest.hexdigest(),examples_seen=seen,
                parameters=sum(p.numel() for p in model.parameters()),numeric_weight_bytes=numeric_weight_bytes(model),
                file_bytes=edge.stat().st_size,after_path=rel,artifacts={rel:sha(edge.read_bytes())})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seeds',type=int,nargs='+',default=list(SEEDS));p.add_argument('--threads',type=int,default=DEFAULT_THREADS)
    p.add_argument('--warmup-steps',type=int,default=WARMUP_STEPS)
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    p.add_argument('--baseline',type=Path,default=ROOT/'results/v012/training.json')
    p.add_argument('--model-dir',type=Path,default=ROOT/'models/v012_warmup')
    p.add_argument('--out',type=Path,default=ROOT/'results/v012_warmup/training.json');a=p.parse_args()
    if tuple(a.seeds)!=SEEDS or a.threads!=1: p.error('published warm-up ablation is pinned to seeds 11/22/33 and one thread')
    torch.set_num_threads(a.threads);torch.use_deterministic_algorithms(True)
    baseline=json.loads(a.baseline.read_text());data,_=load_dataset(a.data)
    digest=sha((a.data/'manifest.json').read_bytes())
    if digest!=baseline.get('dataset_sha256'): raise ValueError('dataset differs from frozen baseline')
    groups={}
    for row in data['train']: groups.setdefault(row['task'],[]).append(row)
    model_dir=repo_path(a.model_dir);started=time.perf_counter();runs=[]
    for seed in a.seeds:
        plan=baseline_plan(baseline,seed)
        if plan['target_steps']!=target_steps(seed): raise ValueError('baseline step count changed')
        runs.append(train(seed,plan,a.threads,data,groups,digest,model_dir,a.warmup_steps))
    report=dict(protocol='two-block new-block-only warm-up then joint fine-tuning; frozen one-block data stream',
                warmup_steps=a.warmup_steps,seeds=a.seeds,threads=a.threads,dataset_sha256=digest,
                expected=len(a.seeds),completed=len(runs),runs=runs,wall_seconds=time.perf_counter()-started,energy_joules=None)
    out=repo_path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(completed=len(runs),out=str(out))),flush=True)

if __name__=='__main__': main()
