#!/usr/bin/env python3
"""v0.14 byte-token ablation for sealed generalization tests.

Remaps an instruction BPE Transformer to a pure-byte instruction tokenizer
while preserving all internal Transformer weights and logits for the 256 byte
rows plus BOS/RESPONSE/EOS. Training then uses the same frozen synthetic data.
"""
import argparse,copy,hashlib,json,platform,random,sys,time
from pathlib import Path
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'benchmarks'))

from byte_bpe import ByteBPE
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss
from transformer_model import TinyTransformer,export_transformer,numeric_weight_bytes
from instruction_blocks_v012 import promote_blocks,repo_output_dir,save

SEEDS=(11,22,33)
ARCHITECTURES=(1,2)
DEFAULT_THREADS=1
DEFAULT_CPU_SECONDS=60.0

def remap_to_byte_model(model,old_tok):
    if not isinstance(model,TinyTransformer) or not isinstance(old_tok,ByteBPE):
        raise TypeError('expected TinyTransformer and ByteBPE')
    if not old_tok.instruction or model.vocab_size!=old_tok.vocab_size:
        raise ValueError('source must use matching instruction BPE')
    new_tok=ByteBPE((),instruction=True)
    cfg=model.export_config();cfg['vocab_size']=new_tok.vocab_size
    target=TinyTransformer(**cfg)
    for i,(src,dst) in enumerate(zip(model.blocks,target.blocks)):
        dst.load_state_dict(src.state_dict())
    keep=list(range(256))+[old_tok.bos_id,old_tok.response_id,old_tok.eos_id]
    if len(set(keep))!=259:
        raise ValueError('invalid source special-token mapping')
    with torch.no_grad():
        target.emb.weight.copy_(model.emb.weight[keep])
        target.out.weight.copy_(model.out.weight[keep])
        target.out.bias.copy_(model.out.bias[keep])
    target.train(model.training)
    return target,new_tok

def build_identity(seed,blocks,cpu,threads,dataset_digest,tok_fp,config):
    return dict(protocol='edge-sft-v014-pure-byte-1',seed=int(seed),blocks=int(blocks),
                cpu_budget=float(cpu),threads=int(threads),dataset_sha256=dataset_digest,
                tokenizer_fingerprint=tok_fp,tokenizer_mode='pure-byte-instruction',
                dim=int(config['dim']),hidden=int(config['hidden']),window=int(config['window']),
                precision=str(config['precision']),vocab_size=int(config['vocab_size']),
                batch=16,lr=.001,weight_decay=.01,clip_norm=1.0,max_length=128,
                selection='minimum response validation NLL at 25/50/75/100 percent')

def assert_fair_pair(one,two):
    if one.get('blocks')!=1 or two.get('blocks')!=2:
        raise ValueError('need blocks 1 and 2')
    ignore={'blocks'}
    keys=(set(one)|set(two))-ignore
    changed=[k for k in sorted(keys) if one.get(k)!=two.get(k)]
    if changed:
        raise ValueError('unfair byte-token pair: '+','.join(changed))
    return True

def train_trial(seed,blocks,cpu_seconds,threads,data,groups,dataset_digest,model_dir):
    base_path=ROOT/f'models/external_v06/bpe513-seed{seed}.pt'
    cp=torch.load(base_path,map_location='cpu',weights_only=True)
    base,bpe_tok=expand_checkpoint(cp,seed)
    promoted=promote_blocks(base,blocks,seed)
    model,tok=remap_to_byte_model(promoted,bpe_tok)
    identity=build_identity(seed,blocks,cpu_seconds,threads,dataset_digest,tok.fingerprint(),model.export_config())

    train=data['train'];valid=data['valid']
    for rows in (train,valid):
        for i in range(0,len(rows),16):
            make_batch(rows[i:i+16],tok)

    stem=f'seed{seed}-b{blocks}-byte'
    before=model_dir/(stem+'-before.edge');after=model_dir/(stem+'-after.edge')
    export_transformer(model,before,tokenizer=tok,max_generate=32)
    opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    baseline=validation_loss(model,valid,tok)
    rng=random.Random(7700+seed);tasks=sorted(groups)
    cpu=wall=0.;step=0;threshold=1;best=float('inf');best_state=None;best_step=0
    curve=[];seen={t:0 for t in tasks};digest=hashlib.sha256()
    while cpu<cpu_seconds and step<100000:
        model.train();c0=time.process_time();w0=time.perf_counter();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);row=rng.choice(groups[task]);batch.append(row)
            seen[task]+=1;digest.update(row['id'].encode())
        x,y=make_batch(batch,tok);opt.zero_grad(set_to_none=True)
        loss=response_loss(model(x),y)
        if not torch.isfinite(loss): raise RuntimeError('nonfinite training loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step()
        cpu+=time.process_time()-c0;wall+=time.perf_counter()-w0;step+=1
        if cpu>=cpu_seconds*threshold/4 or cpu>=cpu_seconds:
            nll=validation_loss(model,valid,tok)
            curve.append(dict(step=step,train_cpu_seconds=cpu,validation_nll=nll))
            if nll<best:
                best=nll;best_state=copy.deepcopy(model.state_dict());best_step=step
            threshold+=1
            print(json.dumps(dict(seed=seed,blocks=blocks,step=step,validation_nll=nll)),flush=True)
    if best_state is None: raise RuntimeError('no validation checkpoint')
    model.load_state_dict(best_state);model.eval()
    export_transformer(model,after,tokenizer=tok,max_generate=32)
    rel=str(after.relative_to(ROOT))
    return dict(seed=seed,blocks=blocks,identity=identity,source_checkpoint_sha256=sha(base_path.read_bytes()),
                parameters=sum(p.numel() for p in model.parameters()),steps=step,selected_step=best_step,
                train_cpu_seconds=cpu,train_wall_seconds=wall,before_validation_nll=baseline,
                selected_validation_nll=best,validation_curve=curve,examples_seen=seen,
                batch_ids_sha256=digest.hexdigest(),before_path=str(before.relative_to(ROOT)),
                after_path=rel,file_bytes=after.stat().st_size,numeric_weight_bytes=numeric_weight_bytes(model),
                cache_payload_bytes=8*blocks*model.window*model.dim,
                artifacts={rel:sha(after.read_bytes())})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cpu-seconds',type=float,default=DEFAULT_CPU_SECONDS)
    p.add_argument('--seeds',type=int,nargs='+',default=list(SEEDS))
    p.add_argument('--threads',type=int,default=DEFAULT_THREADS)
    p.add_argument('--architectures',type=int,nargs='+',default=list(ARCHITECTURES))
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v013')
    p.add_argument('--out',type=Path,default=ROOT/'results/v014/training.json')
    p.add_argument('--model-dir',type=Path,default=ROOT/'models/v014')
    a=p.parse_args()
    if not 0<a.cpu_seconds<=3600 or a.threads!=1 or tuple(a.seeds)!=SEEDS or tuple(a.architectures)!=ARCHITECTURES:
        p.error('published v0.14 ablation is pinned to 60s-style paired seeds 11/22/33, blocks 1/2, one thread')
    torch.set_num_threads(a.threads);torch.use_deterministic_algorithms(True)
    data,_=load_dataset(a.data);groups={}
    for row in data['train']: groups.setdefault(row['task'],[]).append(row)
    digest=sha((a.data/'manifest.json').read_bytes())
    model_dir=repo_output_dir(a.model_dir);model_dir.mkdir(parents=True,exist_ok=True)
    report=dict(protocol='same v0.13 curriculum and CPU budget; pure-byte tokenizer; paired block count',
                cpu_budget_seconds=a.cpu_seconds,seeds=a.seeds,architectures=a.architectures,threads=a.threads,
                expected=6,dataset_sha256=digest,runs=[],synthetic=True,energy_joules=None,
                torch=str(torch.__version__),platform=platform.platform())
    for seed in a.seeds:
        pair=[]
        for blocks in a.architectures:
            row=train_trial(seed,blocks,a.cpu_seconds,a.threads,data,groups,digest,model_dir)
            report['runs'].append(row);pair.append(row);report['completed']=len(report['runs']);save(a.out,report)
        assert_fair_pair(pair[0]['identity'],pair[1]['identity'])
    report['completed']=len(report['runs']);report['fairness_verified']=True;save(a.out,report)
    print(json.dumps(dict(completed=report['completed'],fairness_verified=True,out=str(a.out))),flush=True)

if __name__=='__main__':
    main()
