#!/usr/bin/env python3
"""Controlled v0.12 ablation with an equal optimizer-step budget."""
import argparse,copy,hashlib,json,random,sys,time
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss
from transformer_model import export_transformer,numeric_weight_bytes
from instruction_blocks_v012 import promote_blocks

SEEDS=(11,22,33);ARCHITECTURES=(1,2);DEFAULT_THREADS=1;DEFAULT_STEPS=9000
CONTROL_KEYS=('protocol','seed','step_budget','threads','dataset_sha256','tokenizer_fingerprint','dim','hidden','window','precision','batch','lr','weight_decay','clip_norm','max_length','selection')

def build_identity(seed,blocks,steps,threads,dataset_digest,tok_fp,config):
    return dict(protocol='edge-sft-v012-equal-steps-1',seed=int(seed),step_budget=int(steps),threads=int(threads),
        dataset_sha256=dataset_digest,tokenizer_fingerprint=tok_fp,dim=int(config['dim']),hidden=int(config['hidden']),
        window=int(config['window']),precision=str(config['precision']),batch=16,lr=.001,weight_decay=.01,
        clip_norm=1.0,max_length=128,selection='minimum response validation NLL at 25/50/75/100 percent',blocks=int(blocks))

def assert_fair_pair(one,two):
    if one.get('blocks')!=1 or two.get('blocks')!=2: raise ValueError('need blocks 1 and 2')
    changed=[k for k in CONTROL_KEYS if one.get(k)!=two.get(k)]
    if changed: raise ValueError('unfair equal-step pair: '+','.join(changed))
    return True

def train(seed,blocks,steps,threads,data,groups,dataset_digest,model_dir):
    cp=torch.load(ROOT/f'models/external_v06/bpe513-seed{seed}.pt',map_location='cpu',weights_only=True)
    base,tok=expand_checkpoint(cp,seed);model=promote_blocks(base,blocks,seed)
    identity=build_identity(seed,blocks,steps,threads,dataset_digest,tok.fingerprint(),model.export_config())
    rng=random.Random(7700+seed);tasks=sorted(groups);opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    best=float('inf');state=None;best_step=0;curve=[];digest=hashlib.sha256();cpu=0.;wall=0.
    marks={max(1,round(steps*x/4)) for x in (1,2,3,4)}
    for step in range(1,steps+1):
        model.train();c=time.process_time();w=time.perf_counter();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);row=rng.choice(groups[task]);batch.append(row);digest.update(row['id'].encode())
        x,y=make_batch(batch,tok);opt.zero_grad(set_to_none=True);loss=response_loss(model(x),y)
        if not torch.isfinite(loss): raise RuntimeError('nonfinite training loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step()
        cpu+=time.process_time()-c;wall+=time.perf_counter()-w
        if step in marks:
            nll=validation_loss(model,data['valid'],tok);curve.append(dict(step=step,validation_nll=nll))
            if nll<best: best=nll;state=copy.deepcopy(model.state_dict());best_step=step
    model.load_state_dict(state);model.eval();model_dir.mkdir(parents=True,exist_ok=True)
    edge=model_dir/f'equalsteps-seed{seed}-b{blocks}-after.edge';export_transformer(model,edge,tokenizer=tok,max_generate=32)
    rel=str(edge.relative_to(ROOT))
    return dict(seed=seed,blocks=blocks,identity=identity,steps=steps,selected_step=best_step,selected_validation_nll=best,
        validation_curve=curve,train_cpu_seconds=cpu,train_wall_seconds=wall,parameters=sum(p.numel() for p in model.parameters()),
        file_bytes=edge.stat().st_size,numeric_weight_bytes=numeric_weight_bytes(model),batch_ids_sha256=digest.hexdigest(),
        after_path=rel,artifacts={rel:sha(edge.read_bytes())})

def main():
    p=argparse.ArgumentParser();p.add_argument('--steps',type=int,default=DEFAULT_STEPS);p.add_argument('--seeds',type=int,nargs='+',default=list(SEEDS))
    p.add_argument('--threads',type=int,default=DEFAULT_THREADS);p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    p.add_argument('--model-dir',type=Path,default=ROOT/'models/v012_equalsteps');p.add_argument('--out',type=Path,default=ROOT/'results/v012/equal_steps_training.json');a=p.parse_args()
    if not 1<=a.steps<=100000: p.error('invalid step budget')
    torch.set_num_threads(a.threads);torch.use_deterministic_algorithms(True);data,_=load_dataset(a.data);groups={}
    for row in data['train']: groups.setdefault(row['task'],[]).append(row)
    dataset_digest=sha((a.data/'manifest.json').read_bytes());runs=[]
    for seed in a.seeds:
        pair=[]
        for blocks in ARCHITECTURES:
            r=train(seed,blocks,a.steps,a.threads,data,groups,dataset_digest,a.model_dir);runs.append(r);pair.append(r)
            print(json.dumps({k:r[k] for k in ('seed','blocks','steps','train_cpu_seconds','selected_validation_nll')}),flush=True)
        assert_fair_pair(pair[0]['identity'],pair[1]['identity'])
    report=dict(protocol='same frozen data, sampler, optimizer and optimizer-step budget; only block count differs',
        steps=a.steps,seeds=a.seeds,architectures=list(ARCHITECTURES),threads=a.threads,dataset_sha256=dataset_digest,
        expected=len(a.seeds)*2,completed=len(runs),fairness_verified=True,runs=runs)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
