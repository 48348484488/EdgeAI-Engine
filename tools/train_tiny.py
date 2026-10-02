#!/usr/bin/env python3
"""Train a tiny byte-level EdgeAI v0.2 model and export the native .edge format.
Training uses PyTorch; inference does not. This script is intentionally small and CPU-friendly.
"""
import argparse, math, struct, pathlib
import torch
import torch.nn as nn
import torch.nn.functional as F

class BitLinear(nn.Linear):
    def forward(self, x):
        w = self.weight
        wc = w - w.mean(dim=1, keepdim=True)
        scale = wc.abs().mean(dim=1, keepdim=True).clamp_min(1e-5)
        q = (wc / scale).round().clamp(-1, 1) * scale
        wq = wc + (q - wc).detach()
        return F.linear(x, wq, self.bias)

class TinyEdge(nn.Module):
    def __init__(self, dim=64, hidden=128, loops=2):
        super().__init__(); self.dim=dim; self.hidden=hidden; self.loops=loops
        self.emb=nn.Embedding(256,dim); self.wx=BitLinear(dim,dim); self.wh=BitLinear(dim,dim)
        self.up=BitLinear(dim,hidden); self.down=BitLinear(hidden,dim); self.out=nn.Linear(dim,256)
    def reason(self,h):
        for _ in range(self.loops):
            z=F.layer_norm(h,(self.dim,)); h=h+0.5*self.down(F.silu(self.up(z)))
        return h
    def forward(self,x):
        B,T=x.shape; h=torch.zeros(B,self.dim,device=x.device); ys=[]
        for t in range(T):
            e=self.emb(x[:,t]); h=torch.tanh(self.wx(e)+self.wh(h)); q=self.reason(h); ys.append(self.out(q))
        return torch.stack(ys,1)

def pack_ternary(weight, bias):
    w=weight.detach().float().cpu(); wc=w-w.mean(1,keepdim=True); scale=wc.abs().mean(1).clamp_min(1e-5); q=(wc/scale[:,None]).round().clamp(-1,1).to(torch.int8)
    flat=q.flatten().tolist(); packed=bytearray((len(flat)+3)//4)
    for i,v in enumerate(flat):
        code=1 if v>0 else (2 if v<0 else 0); packed[i//4] |= code << ((i%4)*2)
    b=torch.zeros(w.shape[0]) if bias is None else bias.detach().float().cpu()
    return packed,scale,b

def w_u32(f,x): f.write(struct.pack('<I',int(x)))
def w_u64(f,x): f.write(struct.pack('<Q',int(x)))
def w_f32(f,x): f.write(struct.pack('<f',float(x)))
def write_floats(f,t): f.write(t.detach().float().cpu().contiguous().numpy().astype('<f4').tobytes())
def write_ternary(f,layer):
    p,s,b=pack_ternary(layer.weight,layer.bias); w_u32(f,layer.out_features);w_u32(f,layer.in_features);w_u64(f,len(p));f.write(p);write_floats(f,s);write_floats(f,b)
def write_dense(f,layer): w_u32(f,layer.out_features);w_u32(f,layer.in_features);write_floats(f,layer.weight);write_floats(f,layer.bias)
def export(m,path,max_generate=96,confidence=.92):
    with open(path,'wb') as f:
        f.write(b'EDGEAI2\0');w_u32(f,2);w_u32(f,256);w_u32(f,m.dim);w_u32(f,m.hidden);w_u32(f,m.loops);w_u32(f,max_generate);w_f32(f,confidence)
        w_u64(f,m.emb.weight.numel());write_floats(f,m.emb.weight);write_ternary(f,m.wx);write_ternary(f,m.wh);write_ternary(f,m.up);write_ternary(f,m.down);write_dense(f,m.out)

def batch(data,seq,batch_size):
    max_start=len(data)-seq-1
    idx=torch.randint(0,max_start,(batch_size,)); x=torch.stack([data[i:i+seq] for i in idx]); y=torch.stack([data[i+1:i+seq+1] for i in idx]); return x,y

def main():
    ap=argparse.ArgumentParser();ap.add_argument('text');ap.add_argument('--out',default='models/tiny.edge');ap.add_argument('--dim',type=int,default=64);ap.add_argument('--hidden',type=int,default=128);ap.add_argument('--loops',type=int,default=2);ap.add_argument('--seq',type=int,default=64);ap.add_argument('--batch',type=int,default=8);ap.add_argument('--steps',type=int,default=400);ap.add_argument('--lr',type=float,default=2e-3);args=ap.parse_args()
    torch.manual_seed(42);torch.set_num_threads(min(4,torch.get_num_threads()));raw=pathlib.Path(args.text).read_bytes();
    if len(raw)<args.seq+2: raw=(raw+b'\n')*((args.seq+2)//max(1,len(raw))+2)
    data=torch.tensor(list(raw),dtype=torch.long);m=TinyEdge(args.dim,args.hidden,args.loops);opt=torch.optim.AdamW(m.parameters(),lr=args.lr)
    for s in range(args.steps):
        x,y=batch(data,args.seq,args.batch);z=m(x);loss=F.cross_entropy(z.reshape(-1,256),y.reshape(-1));opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(m.parameters(),1);opt.step()
        if (s+1)%max(1,args.steps//10)==0: print(f'step {s+1}/{args.steps} loss={loss.item():.4f}')
    pathlib.Path(args.out).parent.mkdir(parents=True,exist_ok=True);export(m,args.out);print('saved',args.out)
if __name__=='__main__': main()
