#!/usr/bin/env python3
"""Research benchmark: v0.2 ternary recurrent core vs a similarly sized Transformer.
Synthetic task: copy 12 random byte-like symbols after a gap. This measures precise
long-range retrieval, not general language ability.
"""
import os,time,torch
import torch.nn as nn
import torch.nn.functional as F

torch.manual_seed(12); torch.set_num_threads(min(4,os.cpu_count() or 1))
V=66; D=48; H=96; L=48; B=32

def batch(bs=B):
    first=torch.randint(2,V,(bs,12)); filler=torch.randint(2,V,(bs,L-25))
    seq=torch.cat([first,torch.ones(bs,1,dtype=torch.long),filler,first],1)
    x,y=seq[:,:-1],seq[:,1:]; mask=torch.zeros_like(y,dtype=torch.float32);mask[:,-12:]=1
    return x,y,mask

class BitLinear(nn.Linear):
    def forward(self,x):
        w=self.weight;wc=w-w.mean(1,keepdim=True);s=wc.abs().mean(1,keepdim=True).clamp_min(1e-5);q=(wc/s).round().clamp(-1,1)*s;wq=wc+(q-wc).detach();return F.linear(x,wq,self.bias)

class EdgeCore(nn.Module):
    def __init__(self):
        super().__init__();self.e=nn.Embedding(V,D);self.wx=BitLinear(D,D);self.wh=BitLinear(D,D);self.up=BitLinear(D,H);self.down=BitLinear(H,D);self.o=nn.Linear(D,V)
    def forward(self,x):
        h=torch.zeros(x.size(0),D);outs=[]
        for t in range(x.size(1)):
            h=torch.tanh(self.wx(self.e(x[:,t]))+self.wh(h));z=F.layer_norm(h,(D,));q=h+.5*self.down(F.silu(self.up(z)));outs.append(self.o(q))
        return torch.stack(outs,1)

class TinyTransformer(nn.Module):
    def __init__(self):
        super().__init__();self.e=nn.Embedding(V,D);self.p=nn.Parameter(torch.randn(1,L,D)*.01);layer=nn.TransformerEncoderLayer(D,4,H,batch_first=True,norm_first=True,dropout=0);self.tr=nn.TransformerEncoder(layer,1);self.o=nn.Linear(D,V)
    def forward(self,x):
        n=x.size(1);h=self.e(x)+self.p[:,:n];m=torch.triu(torch.ones(n,n,dtype=torch.bool),1);return self.o(self.tr(h,mask=m,is_causal=True))

def run(name,m,steps=250):
    opt=torch.optim.AdamW(m.parameters(),lr=3e-3);start=time.perf_counter()
    for _ in range(steps):
        x,y,mask=batch();z=m(x);ce=F.cross_entropy(z.reshape(-1,V),y.reshape(-1),reduction='none').view_as(y);loss=(ce*mask).sum()/mask.sum();opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(m.parameters(),1);opt.step()
    sec=time.perf_counter()-start
    with torch.no_grad():
        acc=[]
        for _ in range(20):
            x,y,mask=batch(64);p=m(x).argmax(-1);s=mask.bool();acc.append((p[s]==y[s]).float().mean().item())
    print(f'{name}: params={sum(p.numel() for p in m.parameters())} accuracy={sum(acc)/len(acc):.4f} train_steps_per_s={steps/sec:.2f} final_loss={loss.item():.4f}')

run('edge_ternary_recurrent_v02',EdgeCore())
run('transformer_1layer',TinyTransformer())
