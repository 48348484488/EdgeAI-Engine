#!/usr/bin/env python3
"""Train stabilized two-block candidates on the v0.13 length-bridge curriculum."""
import argparse,copy,json,random,sys,time
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss
from transformer_model import export_transformer,numeric_weight_bytes
from instruction_blocks_v012 import repo_path
from instruction_blocks_equal_steps_v012 import promote_for_init,make_optimizer

SEEDS=(11,22,33);CPU_SECONDS=60.0;THREADS=1;INIT_MODE='copy_inner_identity';INNER_LR_SCALE=.25

def train_trial(seed,data,groups,dataset_digest,model_dir):
    base_path=ROOT/f'models/external_v06/bpe513-seed{seed}.pt'
    cp=torch.load(base_path,map_location='cpu',weights_only=True)
    base,tok=expand_checkpoint(cp,seed);model=promote_for_init(base,seed,INIT_MODE)
    opt=make_optimizer(model,INNER_LR_SCALE);rng=random.Random(7700+seed);tasks=sorted(groups)
    best=float('inf');best_state=None;best_step=0;curve=[];cpu=wall=0.;step=0;threshold=1
    for rows in (data['train'],data['valid']):
        for i in range(0,len(rows),16): make_batch(rows[i:i+16],tok)
    while cpu<CPU_SECONDS and step<100000:
        model.train();c0=time.process_time();w0=time.perf_counter();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);batch.append(rng.choice(groups[task]))
        x,y=make_batch(batch,tok);opt.zero_grad(set_to_none=True);loss=response_loss(model(x),y)
        if not torch.isfinite(loss): raise RuntimeError('nonfinite training loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step()
        cpu+=time.process_time()-c0;wall+=time.perf_counter()-w0;step+=1
        if cpu>=CPU_SECONDS*threshold/4 or cpu>=CPU_SECONDS:
            nll=validation_loss(model,data['valid'],tok)
            curve.append(dict(step=step,train_cpu_seconds=cpu,validation_nll=nll))
            if nll<best:best=nll;best_state=copy.deepcopy(model.state_dict());best_step=step
            threshold+=1
    if best_state is None:raise RuntimeError('no validation checkpoint')
    model.load_state_dict(best_state);model.eval();model_dir.mkdir(parents=True,exist_ok=True)
    edge=model_dir/f'seed{seed}-b2-copy-inner-lr025.edge';export_transformer(model,edge,tokenizer=tok,max_generate=32)
    rel=str(edge.relative_to(ROOT))
    return dict(seed=seed,blocks=2,init_mode=INIT_MODE,block1_inner_lr_scale=INNER_LR_SCALE,
        cpu_budget_seconds=CPU_SECONDS,steps=step,selected_step=best_step,selected_validation_nll=best,
        validation_curve=curve,train_cpu_seconds=cpu,train_wall_seconds=wall,
        parameters=sum(p.numel() for p in model.parameters()),file_bytes=edge.stat().st_size,
        numeric_weight_bytes=numeric_weight_bytes(model),model_path=rel,model_sha256=sha(edge.read_bytes()),
        source_checkpoint_sha256=sha(base_path.read_bytes()),dataset_sha256=dataset_digest)

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v013_length')
    p.add_argument('--out',type=Path,default=ROOT/'results/v013_length_stabilized/training.json')
    p.add_argument('--model-dir',type=Path,default=ROOT/'models/v013_length_stabilized');a=p.parse_args()
    torch.set_num_threads(THREADS);torch.use_deterministic_algorithms(True);data,_=load_dataset(a.data)
    digest=sha((a.data/'manifest.json').read_bytes());groups={}
    for row in data['train']:groups.setdefault(row['task'],[]).append(row)
    model_dir=repo_path(a.model_dir);runs=[]
    for seed in SEEDS:
        r=train_trial(seed,data,groups,digest,model_dir);runs.append(r)
        print(json.dumps({k:r[k] for k in ('seed','steps','selected_step','selected_validation_nll','train_cpu_seconds')}),flush=True)
    report=dict(protocol='v0.13 length bridge; two-block copy-inner identity with 0.25x inner LR; 60 CPU seconds',
        seeds=list(SEEDS),blocks=2,threads=THREADS,cpu_budget_seconds=CPU_SECONDS,
        init_mode=INIT_MODE,block1_inner_lr_scale=INNER_LR_SCALE,dataset_sha256=digest,
        expected=3,completed=len(runs),runs=runs)
    out=repo_path(a.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
