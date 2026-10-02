#!/usr/bin/env python3
"""Equal-update ablation for EdgeAI v0.12 one versus two Transformer blocks."""
import argparse,copy,hashlib,json,platform,random,sys,time
from pathlib import Path
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss
from transformer_model import export_transformer,numeric_weight_bytes
from instruction_blocks_v012 import promote_blocks,save,repo_output_dir

DEFAULT_TARGETS={11:11269,22:11286,33:9661}

def target_for(seed,targets=None):
    targets=DEFAULT_TARGETS if targets is None else targets
    if seed not in targets or int(targets[seed])<1: raise ValueError('missing positive step target')
    return int(targets[seed])

def train(seed,blocks,target,threads,data,groups,digest,model_dir,base_path):
    checkpoint=torch.load(base_path,map_location='cpu',weights_only=True)
    base,tok=expand_checkpoint(checkpoint,seed);model=promote_blocks(base,blocks,seed)
    identity=dict(protocol='edge-sft-v012-equal-updates-1',seed=seed,blocks=blocks,target_steps=target,
                  threads=threads,dataset_sha256=digest,tokenizer_fingerprint=tok.fingerprint(),
                  batch=16,lr=.001,weight_decay=.01,clip_norm=1.0,max_length=128)
    valid=data['valid']
    for rows in (data['train'],valid):
        for i in range(0,len(rows),16): make_batch(rows[i:i+16],tok)
    stem=f'equal-steps-seed{seed}-b{blocks}';before=model_dir/(stem+'-before.edge');after=model_dir/(stem+'-after.edge')
    export_transformer(model,before,tokenizer=tok,max_generate=32)
    optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    baseline=validation_loss(model,valid,tok);rng=random.Random(7700+seed);tasks=sorted(groups)
    best=float('inf');best_state=None;best_step=0;curve=[];seen={t:0 for t in tasks}
    ids=hashlib.sha256();cpu0=time.process_time();wall0=time.perf_counter();milestones={max(1,round(target*q/4)) for q in (1,2,3,4)}
    for step in range(1,target+1):
        model.train();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);row=rng.choice(groups[task]);batch.append(row);seen[task]+=1;ids.update(row['id'].encode())
        x,y=make_batch(batch,tok);optimizer.zero_grad(set_to_none=True);loss=response_loss(model(x),y)
        if not torch.isfinite(loss): raise RuntimeError('nonfinite training loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        if step in milestones:
            metric=validation_loss(model,valid,tok);curve.append(dict(step=step,validation_nll=metric))
            if metric<best: best=metric;best_state=copy.deepcopy(model.state_dict());best_step=step
            print(json.dumps(dict(seed=seed,blocks=blocks,step=step,validation_nll=metric)),flush=True)
    cpu=time.process_time()-cpu0;wall=time.perf_counter()-wall0
    if best_state is None: raise RuntimeError('no validation checkpoint')
    model.load_state_dict(best_state);model.eval();export_transformer(model,after,tokenizer=tok,max_generate=32)
    return dict(seed=seed,blocks=blocks,identity=identity,parameters=sum(p.numel() for p in model.parameters()),
                steps=target,selected_step=best_step,train_cpu_seconds=cpu,train_wall_seconds=wall,
                before_validation_nll=baseline,selected_validation_nll=best,validation_curve=curve,
                examples_seen=seen,batch_ids_sha256=ids.hexdigest(),before_path=str(before.relative_to(ROOT)),
                after_path=str(after.relative_to(ROOT)),file_bytes=after.stat().st_size,
                numeric_weight_bytes=numeric_weight_bytes(model),cache_payload_bytes=8*blocks*model.window*model.dim,
                artifacts={str(after.relative_to(ROOT)):sha(after.read_bytes())})

def main():
    p=argparse.ArgumentParser();p.add_argument('--seeds',type=int,nargs='+',default=[11,22,33]);p.add_argument('--threads',type=int,default=1)
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07');p.add_argument('--out',type=Path,default=ROOT/'results/v012/equal_steps_training.json')
    p.add_argument('--model-dir',type=Path,default=ROOT/'models/v012-equal-steps');a=p.parse_args()
    torch.set_num_threads(a.threads);torch.use_deterministic_algorithms(True);data,_=load_dataset(a.data);groups={}
    for row in data['train']: groups.setdefault(row['task'],[]).append(row)
    a.model_dir=repo_output_dir(a.model_dir);a.model_dir.mkdir(parents=True,exist_ok=True);digest=sha((a.data/'manifest.json').read_bytes())
    report=dict(protocol='same frozen data, batch sequence and optimizer-update count; only block count differs',
                seeds=a.seeds,architectures=[1,2],threads=a.threads,dataset_sha256=digest,runs=[],expected=2*len(a.seeds),
                targets={str(s):target_for(s) for s in a.seeds},synthetic=True,energy_joules=None,torch=str(torch.__version__),platform=platform.platform())
    for seed in a.seeds:
        base=ROOT/f'models/external_v06/bpe513-seed{seed}.pt';target=target_for(seed)
        for blocks in (1,2):
            report['runs'].append(train(seed,blocks,target,a.threads,data,groups,digest,a.model_dir,base));report['completed']=len(report['runs']);save(a.out,report)
    report['fairness_verified']=all(
        next(r for r in report['runs'] if r['seed']==s and r['blocks']==1)['batch_ids_sha256']==next(r for r in report['runs'] if r['seed']==s and r['blocks']==2)['batch_ids_sha256']
        and next(r for r in report['runs'] if r['seed']==s and r['blocks']==1)['steps']==next(r for r in report['runs'] if r['seed']==s and r['blocks']==2)['steps']
        for s in a.seeds)
    save(a.out,report);print(json.dumps(dict(completed=report['completed'],fairness_verified=report['fairness_verified'])))

if __name__=='__main__': main()
