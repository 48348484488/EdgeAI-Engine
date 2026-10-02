#!/usr/bin/env python3
"""Equal-step ablation: train two-block v0.12 models to the one-block step counts."""
import argparse,copy,hashlib,json,random,sys,time
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss
from transformer_model import export_transformer,numeric_weight_bytes
from instruction_blocks_v012 import promote_blocks

TARGET_STEPS={11:11269,22:11286,33:9661}

def target_steps(seed):
    if seed not in TARGET_STEPS: raise ValueError('no frozen one-block target for seed')
    return TARGET_STEPS[seed]

def train(seed,steps,data,groups,model_dir):
    base_path=ROOT/f'models/external_v06/bpe513-seed{seed}.pt'
    cp=torch.load(base_path,map_location='cpu',weights_only=True)
    base,tok=expand_checkpoint(cp,seed);model=promote_blocks(base,2,seed)
    valid=data['valid'];rng=random.Random(7700+seed);tasks=sorted(groups)
    optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    best=float('inf');best_state=None;best_step=0;curve=[];digest=hashlib.sha256()
    started=time.process_time();marks={max(1,round(steps*x/4)) for x in (1,2,3,4)}
    for step in range(1,steps+1):
        model.train();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);row=rng.choice(groups[task]);batch.append(row);digest.update(row['id'].encode())
        x,y=make_batch(batch,tok);optimizer.zero_grad(set_to_none=True);loss=response_loss(model(x),y)
        if not torch.isfinite(loss): raise RuntimeError('nonfinite training loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        if step in marks:
            metric=validation_loss(model,valid,tok);curve.append(dict(step=step,validation_nll=metric))
            if metric<best: best=metric;best_state=copy.deepcopy(model.state_dict());best_step=step
            print(json.dumps(dict(seed=seed,blocks=2,step=step,validation_nll=metric)),flush=True)
    cpu=time.process_time()-started
    if best_state is None: raise RuntimeError('no validation checkpoint')
    model.load_state_dict(best_state);model.eval();model_dir.mkdir(parents=True,exist_ok=True)
    edge=model_dir/f'seed{seed}-b2-equalsteps.edge'
    export_transformer(model,edge,tokenizer=tok,max_generate=32)
    return dict(seed=seed,blocks=2,target_steps=steps,steps=steps,selected_step=best_step,
                selected_validation_nll=best,validation_curve=curve,train_cpu_seconds=cpu,
                parameters=sum(p.numel() for p in model.parameters()),file_bytes=edge.stat().st_size,
                numeric_weight_bytes=numeric_weight_bytes(model),batch_ids_sha256=digest.hexdigest(),
                model_path=str(edge.relative_to(ROOT)),model_sha256=sha(edge.read_bytes()))

def main():
    p=argparse.ArgumentParser();p.add_argument('--seeds',type=int,nargs='+',default=[11,22,33])
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    p.add_argument('--model-dir',type=Path,default=ROOT/'models/v012_equalsteps')
    p.add_argument('--out',type=Path,default=ROOT/'results/v012/equal_steps_training.json');a=p.parse_args()
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    data,_=load_dataset(a.data);groups={}
    for row in data['train']: groups.setdefault(row['task'],[]).append(row)
    runs=[train(s,target_steps(s),data,groups,a.model_dir) for s in a.seeds]
    report=dict(protocol='two-block extension trained to frozen one-block optimizer-step counts',
                controls='same base checkpoints, data, batch sampler, batch=16, lr=.001, weight_decay=.01, clip=1, threads=1',
                targets=TARGET_STEPS,runs=runs,completed=len(runs))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(completed=len(runs),out=str(a.out))))

if __name__=='__main__': main()
