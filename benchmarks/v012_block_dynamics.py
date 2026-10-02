#!/usr/bin/env python3
"""Probe early optimization dynamics of the v0.12 identity-initialized second block."""
import argparse,json,math,random,sys
from pathlib import Path
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss
from instruction_blocks_v012 import promote_blocks,repo_path

SEEDS=(11,22,33)
DEFAULT_STEPS=128
PROBES=(1,2,8,32,128)

def group_name(name):
    if name.startswith('blocks.0.'): return 'block0'
    if name.startswith('blocks.1.project.') or name.startswith('blocks.1.down.'): return 'block1_output'
    if name.startswith('blocks.1.'): return 'block1_inner'
    return 'shared'

def l2(values):
    return math.sqrt(sum(float((v.float()*v.float()).sum().item()) for v in values)) if values else 0.0

def group_counts(model):
    out={}
    for name,p in model.named_parameters():
        out[group_name(name)]=out.get(group_name(name),0)+p.numel()
    return out

def grad_norms(model):
    groups={};counts=group_counts(model)
    for name,p in model.named_parameters():
        if p.grad is not None: groups.setdefault(group_name(name),[]).append(p.grad.detach())
    out={}
    for k,v in groups.items():
        z=l2(v);out[k]=dict(l2=z,rms=z/math.sqrt(counts[k]),parameters=counts[k])
    return out

def drift_norms(model,initial):
    groups={};initial_groups={};counts=group_counts(model)
    for name,p in model.named_parameters():
        k=group_name(name);groups.setdefault(k,[]).append(p.detach()-initial[name]);initial_groups.setdefault(k,[]).append(initial[name])
    out={}
    for k,v in groups.items():
        d=l2(v);base=l2(initial_groups[k])
        out[k]=dict(l2=d,rms=d/math.sqrt(counts[k]),relative=d/base if base else None,parameters=counts[k])
    return out

def run_seed(seed,steps,data,groups):
    cp=torch.load(ROOT/f'models/external_v06/bpe513-seed{seed}.pt',map_location='cpu',weights_only=True)
    base,tok=expand_checkpoint(cp,seed);model=promote_blocks(base,2,seed)
    initial={n:p.detach().clone() for n,p in model.named_parameters()}
    rng=random.Random(7700+seed);tasks=sorted(groups)
    opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    probes=set(x for x in PROBES if x<=steps);rows=[]
    initial_nll=validation_loss(model,data['valid'],tok)
    for step in range(1,steps+1):
        model.train();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);batch.append(rng.choice(groups[task]))
        x,y=make_batch(batch,tok);opt.zero_grad(set_to_none=True)
        loss=response_loss(model(x),y);loss.backward()
        if step in probes:
            before=grad_norms(model)
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step()
        if step in probes:
            rows.append(dict(step=step,loss=float(loss.item()),gradient_l2=before,drift_l2=drift_norms(model,initial)))
    final_nll=validation_loss(model,data['valid'],tok)
    return dict(seed=seed,steps=steps,initial_validation_nll=initial_nll,final_validation_nll=final_nll,probes=rows)

def summarize(runs):
    first=[r['probes'][0] for r in runs]
    return dict(
        seeds=[r['seed'] for r in runs],
        first_step_block1_inner_grad_rms=[p['gradient_l2'].get('block1_inner',{}).get('rms',0.0) for p in first],
        first_step_block1_output_grad_rms=[p['gradient_l2'].get('block1_output',{}).get('rms',0.0) for p in first],
        first_step_block0_grad_rms=[p['gradient_l2'].get('block0',{}).get('rms',0.0) for p in first],
        note='project/down are zero-initialized to preserve the original function; inner second-block gradients can therefore start at zero',
    )

def main():
    p=argparse.ArgumentParser();p.add_argument('--steps',type=int,default=DEFAULT_STEPS)
    p.add_argument('--seeds',type=int,nargs='+',default=list(SEEDS));p.add_argument('--threads',type=int,default=1)
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    p.add_argument('--out',type=Path,default=ROOT/'results/v012/block_dynamics.json');a=p.parse_args()
    if not 1<=a.steps<=2048: p.error('steps must be in [1,2048]')
    torch.set_num_threads(a.threads);torch.use_deterministic_algorithms(True)
    data,_=load_dataset(a.data);groups={}
    for row in data['train']: groups.setdefault(row['task'],[]).append(row)
    runs=[run_seed(s,a.steps,data,groups) for s in a.seeds]
    report=dict(protocol='early two-block optimization dynamics on frozen v0.12 data/sampler',
                dataset_sha256=sha((a.data/'manifest.json').read_bytes()),steps=a.steps,runs=runs,summary=summarize(runs))
    out=repo_path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['summary']))

if __name__=='__main__':main()
