#!/usr/bin/env python3
"""Synthetic associative recall, NOT a general-language or Claude benchmark.
Each record is a single symbol encoding (key,value). A query after distractors
asks for one of eight values. All models see the same training batches and test.
"""
import argparse, json, math, statistics, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import torch
from torch import nn
from torch.nn import functional as F
from hybrid_model import HybridTiny

class Transformer(nn.Module):
    def __init__(self,dim=32,hidden=64):
        super().__init__();self.d=dim
        self.emb=nn.Embedding(256,dim);self.pos=nn.Parameter(torch.randn(1,64,dim)*.02)
        self.ln1=nn.LayerNorm(dim);self.qkv=nn.Linear(dim,dim*3);self.project=nn.Linear(dim,dim)
        self.ln2=nn.LayerNorm(dim);self.up=nn.Linear(dim,hidden);self.down=nn.Linear(hidden,dim)
        self.final=nn.LayerNorm(dim);self.out=nn.Linear(dim,256)
    def forward(self,x):
        b,t=x.shape;h=self.emb(x)+self.pos[:,:t];z=self.qkv(self.ln1(h)).reshape(b,t,3,4,self.d//4)
        q,k,v=[a.transpose(1,2) for a in z.unbind(2)]
        a=F.scaled_dot_product_attention(q,k,v,is_causal=True).transpose(1,2).reshape(b,t,self.d)
        h=h+self.project(a);h=h+self.down(F.gelu(self.up(self.ln2(h))))
        return self.out(self.final(h))

def batch(size,length,generator):
    keys=torch.rand(size,8,generator=generator).argsort(1)[:,:6]
    values=torch.randint(0,8,(size,6),generator=generator)
    query=torch.randint(0,6,(size,),generator=generator);rows=torch.arange(size)
    x=torch.randint(80,84,(size,length),generator=generator)
    x[:,:6]=1+8*keys+values
    x[:,-1]=96+keys[rows,query]
    target=112+values[rows,query]
    return x,target

def run(kind,seed,args,test):
    torch.manual_seed(seed)
    model=Transformer() if kind=="transformer_fp32" else HybridTiny(32,64,16,16,1,ternary="ternary" in kind,adaptive_gates="adaptive" in kind)
    optimizer=torch.optim.AdamW(model.parameters(),lr=.002)
    generator=torch.Generator().manual_seed(8100+seed)
    start=time.perf_counter();cpu_start=time.process_time();curve=[]
    for step in range(1,args.steps+1):
        x,y=batch(32,32,generator);z=model(x)[:,-1];loss=F.cross_entropy(z,y)
        optimizer.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1);optimizer.step()
        if step%100==0:curve.append(dict(step=step,loss=loss.item()))
    elapsed=time.perf_counter()-start;cpu=time.process_time()-cpu_start;correct=0
    model.eval()
    with torch.inference_mode():
        for x,y in test:correct+=int((model(x)[:,-1].argmax(-1)==y).sum())
    result=dict(kind=kind,seed=seed,parameters=sum(p.numel() for p in model.parameters()),steps=args.steps,training_examples=args.steps*32,accuracy=correct/args.test_size,correct=correct,total=args.test_size,train_seconds=elapsed,train_cpu_seconds=cpu,energy_joules=None,curve=curve)
    print(json.dumps(result),flush=True);return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--steps",type=int,default=400);ap.add_argument("--seeds",type=int,nargs="+",default=[11,22,33]);ap.add_argument("--test-size",type=int,default=1024);ap.add_argument("--threads",type=int,default=1);ap.add_argument("--out",type=Path,default=Path("results/quality.json"));args=ap.parse_args()
    if args.test_size%32 or args.steps<1 or args.threads<1:ap.error("test-size must be a multiple of 32; positive steps and threads")
    torch.set_num_threads(args.threads);g=torch.Generator().manual_seed(119371)
    test=[batch(32,32,g) for _ in range(args.test_size//32)]
    rows=[]
    for seed in args.seeds:
        for kind in ["hybrid_static_fp32","hybrid_static_ternary","hybrid_adaptive_fp32","hybrid_adaptive_ternary","transformer_fp32"]:
            rows.append(run(kind,seed,args,test))
    groups={}
    for kind in ["hybrid_static_fp32","hybrid_static_ternary","hybrid_adaptive_fp32","hybrid_adaptive_ternary","transformer_fp32"]:
        selection=[r for r in rows if r["kind"]==kind]
        groups[kind]=dict(mean_accuracy=statistics.mean(r["accuracy"] for r in selection),min_accuracy=min(r["accuracy"] for r in selection),max_accuracy=max(r["accuracy"] for r in selection),mean_train_seconds=statistics.mean(r["train_seconds"] for r in selection),parameters=selection[0]["parameters"])
    report=dict(task="symbolic associative recall; 6 joint key/value records, 8 candidate values, query at position 32",caveat="joint symbols simplify binding; not natural language; no claim about general intelligence",chance_among_8_values=.125,sequence_length=32,local_window=16,steps=args.steps,batch_size=32,test_seed=119371,test_size=args.test_size,torch_version=torch.__version__,threads=args.threads,optimizer="AdamW lr=0.002 clip_norm=1",checkpoint_selection="final fixed step; independent confirmatory test set after static-gate pilot",summary=groups,runs=rows)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(groups,indent=2))
if __name__=="__main__":main()
