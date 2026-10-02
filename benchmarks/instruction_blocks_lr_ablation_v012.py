#!/usr/bin/env python3
"""Targeted v0.12 learning-rate ablation for the unstable two-block seed 33."""
import argparse,copy,json,random,sys,time
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss
from transformer_model import export_transformer
from instruction_blocks_v012 import promote_blocks,repo_path

SEED=33; STEPS=9661; VALIDATION_STEPS=(2502,4946,7326,9661); LRS=(0.0005,0.00075)

def train(lr,data,groups,outdir):
    cp=torch.load(ROOT/'models/external_v06/bpe513-seed33.pt',map_location='cpu',weights_only=True)
    base,tok=expand_checkpoint(cp,SEED);model=promote_blocks(base,2,SEED)
    rng=random.Random(7700+SEED);tasks=sorted(groups);opt=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=.01)
    best=float('inf');state=None;best_step=0;curve=[];cpu=0.
    for step in range(1,STEPS+1):
        model.train();c=time.process_time();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);batch.append(rng.choice(groups[task]))
        x,y=make_batch(batch,tok);opt.zero_grad(set_to_none=True);loss=response_loss(model(x),y)
        if not torch.isfinite(loss): raise RuntimeError('nonfinite loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step();cpu+=time.process_time()-c
        if step in VALIDATION_STEPS:
            nll=validation_loss(model,data['valid'],tok);curve.append(dict(step=step,validation_nll=nll))
            if nll<best: best=nll;state=copy.deepcopy(model.state_dict());best_step=step
    model.load_state_dict(state);model.eval();outdir.mkdir(parents=True,exist_ok=True)
    tag=str(lr).replace('.','p');edge=outdir/f'seed33-b2-lr{tag}.edge'
    export_transformer(model,edge,tokenizer=tok,max_generate=32)
    return dict(seed=SEED,blocks=2,lr=lr,steps=STEPS,selected_step=best_step,selected_validation_nll=best,
                validation_curve=curve,train_cpu_seconds=cpu,model_path=str(edge.relative_to(ROOT)),model_sha256=sha(edge.read_bytes()))

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    p.add_argument('--out',type=Path,default=ROOT/'results/v012_lr_ablation/training.json')
    p.add_argument('--model-dir',type=Path,default=ROOT/'models/v012_lr_ablation');a=p.parse_args()
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);data,_=load_dataset(a.data);groups={}
    for r in data['train']: groups.setdefault(r['task'],[]).append(r)
    runs=[train(lr,data,groups,repo_path(a.model_dir)) for lr in LRS]
    report=dict(protocol='targeted seed33 two-block LR ablation; same data/stream/steps; LR only variable',
                seed=SEED,steps=STEPS,lrs=list(LRS),dataset_sha256=sha((a.data/'manifest.json').read_bytes()),runs=runs)
    out=repo_path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('lr','selected_step','selected_validation_nll','train_cpu_seconds')} for r in runs]))
if __name__=='__main__':main()
