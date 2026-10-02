"""Small causal Transformer reference used by EdgeAI training/export.

Known components, not a novel architecture. W8A32 simulated quantization; FP32
master training. One head per block, sliding-window attention, RoPE and
parameter-free LN. Legacy one-block checkpoint keys are preserved.
"""
import math
import os
import tempfile
from collections import OrderedDict
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from mixed_model import replace_linear, write_mixed, layer_payload_bytes, layer_precision
from train_tiny import write_floats, w_u32, w_u64, w_f32

BLOCK_NAMES=('query','key','value','project','up','down')
NAMES=BLOCK_NAMES+('out',)


class TransformerBlock(nn.Module):
    def __init__(self, dim, hidden, precision):
        super().__init__()
        self.query,self.key,self.value,self.project=(nn.Linear(dim,dim) for _ in range(4))
        self.up,self.down=nn.Linear(dim,hidden),nn.Linear(hidden,dim)
        for name in BLOCK_NAMES:
            setattr(self,name,replace_linear(getattr(self,name),precision))


class TinyTransformer(nn.Module):
    def __init__(self,dim=64,hidden=96,window=64,precision='int8',rope_base=10000.,vocab_size=256,blocks=1):
        super().__init__()
        if not (4<=dim<=2048 and dim%2==0 and 4<=hidden<=8192 and 1<=window<=4096):
            raise ValueError('invalid Transformer dimensions')
        if not 1<=blocks<=8:
            raise ValueError('Transformer blocks must be in [1,8]')
        if precision not in ('fp32','int8','ternary') or not math.isfinite(rope_base) or rope_base<=1:
            raise ValueError('invalid precision/RoPE base')
        if not 256<=vocab_size<=4096:
            raise ValueError('invalid vocabulary')
        self.vocab_size=vocab_size
        self.dim,self.hidden,self.window,self.precision,self.rope_base=dim,hidden,window,precision,rope_base
        self.emb=nn.Embedding(vocab_size,dim)
        self.blocks=nn.ModuleList(TransformerBlock(dim,hidden,precision) for _ in range(blocks))
        self.out=replace_linear(nn.Linear(dim,vocab_size),precision)
        self.register_buffer('inv_freq',torch.tensor([rope_base**(-2*j/dim) for j in range(dim//2)],dtype=torch.float32),persistent=False)

    def export_config(self):
        return dict(dim=self.dim,hidden=self.hidden,window=self.window,precision=self.precision,
                    rope_base=self.rope_base,vocab_size=self.vocab_size,blocks=len(self.blocks))

    def _legacy_layer(self,name):
        if len(self.blocks)!=1:
            raise ValueError(name+' is a legacy one-block alias; select model.blocks[index].'+name)
        return getattr(self.blocks[0],name)

    @property
    def query(self): return self._legacy_layer('query')
    @property
    def key(self): return self._legacy_layer('key')
    @property
    def value(self): return self._legacy_layer('value')
    @property
    def project(self): return self._legacy_layer('project')
    @property
    def up(self): return self._legacy_layer('up')
    @property
    def down(self): return self._legacy_layer('down')

    def state_dict(self,*args,**kwargs):
        state=super().state_dict(*args,**kwargs)
        if len(self.blocks)!=1:
            return state
        legacy=OrderedDict()
        prefix='blocks.0.'
        for key,value in state.items():
            legacy[key[len(prefix):] if key.startswith(prefix) else key]=value
        return legacy

    def load_state_dict(self,state_dict,strict=True,assign=False):
        if len(self.blocks)==1 and any(
            key.startswith(tuple(name+'.' for name in BLOCK_NAMES)) for key in state_dict
        ):
            mapped=OrderedDict()
            for key,value in state_dict.items():
                if key.startswith(tuple(name+'.' for name in BLOCK_NAMES)):
                    mapped['blocks.0.'+key]=value
                else:
                    mapped[key]=value
            state_dict=mapped
        return super().load_state_dict(state_dict,strict=strict,assign=assign)

    def rotate(self,x):
        angles=torch.arange(x.shape[1],device=x.device,dtype=x.dtype)[:,None]*self.inv_freq
        c,s=angles.cos()[None],angles.sin()[None]
        a,b=x[...,0::2],x[...,1::2]
        return torch.stack((a*c-b*s,a*s+b*c),-1).flatten(-2)

    def _forward_block(self,h,block):
        n=F.layer_norm(h,(self.dim,),eps=1e-5)
        q,k=self.rotate(block.query(n)),self.rotate(block.key(n));v=block.value(n)
        t=torch.arange(h.shape[1],device=h.device);distance=t[:,None]-t[None,:]
        scores=q@k.transpose(-1,-2)/math.sqrt(self.dim)
        weights=scores.masked_fill((distance<0)|(distance>=self.window),float('-inf')).softmax(-1)
        h=h+block.project(weights@v)
        h=h+.5*block.down(F.silu(block.up(F.layer_norm(h,(self.dim,),eps=1e-5))))
        return h

    def forward(self,tokens):
        if tokens.ndim!=2 or tokens.shape[1]==0 or tokens.shape[1]>16384:
            raise ValueError('expected nonempty [batch,sequence<=16384] tokens')
        h=self.emb(tokens)
        for block in self.blocks:
            h=self._forward_block(h,block)
        return self.out(F.layer_norm(h,(self.dim,),eps=1e-5))


def numeric_weight_bytes(model):
    block_bytes=sum(layer_payload_bytes(getattr(block,name))
                    for block in model.blocks for name in BLOCK_NAMES)
    return model.emb.weight.numel()*4+block_bytes+layer_payload_bytes(model.out)


def export_transformer(model,path,max_generate=128,tokenizer=None):
    if not isinstance(model,TinyTransformer) or not 1<=max_generate<=4096:
        raise ValueError('invalid model/export limit')
    if len(model.blocks)!=1:
        raise ValueError('multi-block export requires EDGEAI8 support')
    for name,p in model.named_parameters():
        if p.device.type!='cpu' or p.dtype!=torch.float32 or not torch.isfinite(p).all():
            raise ValueError('export needs finite FP32 CPU masters: '+name)
    if any(layer_precision(getattr(model,n))!=model.precision for n in NAMES):
        raise ValueError('precision metadata disagrees with actual layers')
    if tokenizer is None and model.vocab_size!=256:
        raise ValueError('dynamic vocabulary needs embedded tokenizer')
    if tokenizer is not None and model.vocab_size!=tokenizer.vocab_size:
        raise ValueError('tokenizer vocabulary mismatch')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
            tmp=Path(f.name);version=(7 if tokenizer.instruction else 6) if tokenizer is not None else 5
            f.write(('EDGEAI'+str(version)+'\0').encode('ascii'));w_u32(f,version)
            for n in (model.dim,model.hidden,model.window,max_generate):
                w_u32(f,n)
            w_f32(f,model.rope_base)
            if tokenizer is not None:
                w_u32(f,len(tokenizer.merges))
                for a,b in tokenizer.merges:
                    w_u32(f,a);w_u32(f,b)
            w_u64(f,model.emb.weight.numel());write_floats(f,model.emb.weight)
            for name in NAMES:
                write_mixed(f,getattr(model,name))
        os.replace(tmp,path)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()
