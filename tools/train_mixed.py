#!/usr/bin/env python3
"""Train a selective-precision byte model; emits a CPU checkpoint and EDGEAI4.
Validation is a separate input file. A tiny corpus is not evidence of general skill.
"""
import argparse, copy, hashlib, json, math, time
from pathlib import Path
import torch
from torch.nn import functional as F
from mixed_model import MixedHybrid, POLICIES, export_mixed as export, numeric_weight_bytes

def batch(data, seq, size, generator):
    count = len(data) - seq
    if count < 1:
        raise ValueError("dataset must contain at least seq+1 bytes; refusing implicit repetition")
    starts = torch.randint(count, (size,), generator=generator)
    x = torch.stack([data[i:i+seq] for i in starts])
    y = torch.stack([data[i+1:i+seq+1] for i in starts])
    return x, y

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("text"); ap.add_argument("--valid", required=True)
    ap.add_argument("--out",default="models/mixed_tiny.edge")
    for name, default in [("dim",32),("hidden",64),("key-dim",16),("window",16),("loops",1),("seq",32),("batch",8),("steps",160),("threads",1),("seed",42)]:
        ap.add_argument("--"+name,type=int,default=default)
    ap.add_argument("--lr",type=float,default=.002)
    ap.add_argument("--policy",choices=list(POLICIES),default="memory_int8")
    ap.add_argument("--output-precision",choices=["fp32","int8","ternary"],default="fp32")
    args=ap.parse_args()
    if min(args.steps,args.seq,args.batch,args.threads)<=0 or not 0 < args.lr < 1:
        ap.error("steps, sequence, batch and threads must be positive; lr in (0,1)")
    torch.set_num_threads(args.threads);torch.manual_seed(args.seed)
    raw=Path(args.text).read_bytes(); validation=Path(args.valid).read_bytes()
    if raw==validation: ap.error("training and validation files must differ")
    train=torch.tensor(list(raw),dtype=torch.long);valid=torch.tensor(list(validation),dtype=torch.long)
    cfg=dict(dim=args.dim,hidden=args.hidden,key_dim=args.key_dim,window=args.window,loops=args.loops,policy=args.policy,output_precision=args.output_precision)
    model=MixedHybrid(**cfg);optimizer=torch.optim.AdamW(model.parameters(),lr=args.lr)
    generator=torch.Generator().manual_seed(args.seed+100)
    eval_generator=torch.Generator().manual_seed(10291)
    eval_batches=[batch(valid,args.seq,args.batch,eval_generator) for _ in range(8)]
    def evaluate():
        model.eval()
        with torch.inference_mode():
            result=sum(F.cross_entropy(model(x).flatten(0,1),y.flatten()).item() for x,y in eval_batches)/len(eval_batches)
        model.train();return result
    initial=evaluate();best=initial;best_step=0;best_state=copy.deepcopy(model.state_dict());log=[]
    start=time.perf_counter()
    for step in range(1,args.steps+1):
        x,y=batch(train,args.seq,args.batch,generator);z=model(x);loss=F.cross_entropy(z.flatten(0,1),y.flatten())
        if not torch.isfinite(loss):raise RuntimeError("nonfinite training loss")
        optimizer.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        if step==1 or step%max(1,args.steps//8)==0 or step==args.steps:
            val=evaluate();entry=dict(step=step,train_loss=loss.item(),validation_nll=val);log.append(entry);print(json.dumps(entry),flush=True)
            if val<best:best=val;best_step=step;best_state=copy.deepcopy(model.state_dict())
    elapsed=time.perf_counter()-start;model.load_state_dict(best_state);model.eval()
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True);export(model,out)
    torch.save(dict(config=cfg,state_dict=best_state),out.with_suffix(".pt"))
    report=dict(kind="educational_byte_lm_not_general_assistant",seed=args.seed,threads=args.threads,parameters=sum(p.numel() for p in model.parameters()),training_bytes=len(raw),validation_bytes=len(validation),training_sha256=hashlib.sha256(raw).hexdigest(),validation_sha256=hashlib.sha256(validation).hexdigest(),steps=args.steps,best_step=best_step,initial_validation_nll=initial,best_validation_nll=best,bits_per_byte=best/math.log(2),seconds=elapsed,energy_joules=None,export_bytes=out.stat().st_size,numeric_weight_bytes=numeric_weight_bytes(model),config=cfg,history=log)
    out.with_suffix(".training.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
