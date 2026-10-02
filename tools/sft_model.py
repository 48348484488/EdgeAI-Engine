"""Response-only SFT primitives; all gradient masters stay FP32 on CPU."""
import copy
import torch
from torch.nn import functional as F
from byte_bpe import ByteBPE
from transformer_model import TinyTransformer

IGNORE=-100

def tokenizer_from_payload(p):
    kind=p.get('format')
    if kind not in ('edge-byte-bpe-1','edge-byte-bpe-2'):raise ValueError('unknown tokenizer format')
    t=ByteBPE(p['merges'],instruction=kind=='edge-byte-bpe-2')
    if t.payload()!=p:raise ValueError('inconsistent tokenizer payload')
    return t

def expand_checkpoint(checkpoint,seed):
    """Preserve every pretrained content/BOS weight; add RESPONSE and EOS only."""
    old_tok=tokenizer_from_payload(checkpoint['tokenizer'])
    if old_tok.instruction:raise ValueError('expected a v0.6 checkpoint to expand')
    config=copy.deepcopy(checkpoint['config'])
    if config['vocab_size']!=old_tok.vocab_size:raise ValueError('vocabulary mismatch')
    new_tok=ByteBPE(old_tok.merges,instruction=True);config['vocab_size']=new_tok.vocab_size
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed+7000);model=TinyTransformer(**config)
    old=checkpoint['state_dict'];new=model.state_dict();n=old_tok.vocab_size
    if set(old)!=set(new):raise ValueError('state keys mismatch')
    for key,value in old.items():
        if not torch.isfinite(value).all():raise ValueError('nonfinite checkpoint')
        if key in ('emb.weight','out.weight','out.bias'):
            if value.shape!=new[key][:n].shape:raise ValueError('state shape mismatch')
            new[key][:n].copy_(value)
        else:
            if value.shape!=new[key].shape:raise ValueError('state shape mismatch')
            new[key].copy_(value)
    model.load_state_dict(new);return model,new_tok

def encode_example(row,tok,max_length=128):
    if not tok.instruction:raise ValueError('SFT needs instruction tokenizer')
    prefix=tok.encode_prompt(row['prompt']);answer=tok.encode(row['answer'])+[tok.eos_id]
    full=prefix+answer
    if len(full)-1>max_length:raise ValueError('example exceeds max_length; no silent truncation')
    x=full[:-1];y=[IGNORE]*(len(prefix)-1)+answer
    assert len(x)==len(y)
    return x,y

def make_batch(rows,tok,max_length=128):
    if not rows or not 1<=max_length<=4096:raise ValueError('invalid batch/length')
    encoded=[encode_example(r,tok,max_length) for r in rows];width=max(len(x) for x,y in encoded)
    x=torch.full((len(rows),width),tok.eos_id,dtype=torch.long)
    y=torch.full_like(x,IGNORE)
    for i,(a,b) in enumerate(encoded):x[i,:len(a)]=torch.tensor(a);y[i,:len(b)]=torch.tensor(b)
    return x,y

def response_loss(logits,targets):
    if targets.shape!=logits.shape[:-1] or not torch.any(targets!=IGNORE):raise ValueError('no response targets or wrong shapes')
    return F.cross_entropy(logits.flatten(0,1),targets.flatten(),ignore_index=IGNORE)

@torch.inference_mode()
def validation_loss(model,rows,tok,batch_size=16):
    model.eval();total=0.;count=0
    for i in range(0,len(rows),batch_size):
        x,y=make_batch(rows[i:i+batch_size],tok);z=model(x)
        total+=F.cross_entropy(z.flatten(0,1),y.flatten(),ignore_index=IGNORE,reduction='sum').item()
        count+=int((y!=IGNORE).sum())
    return total/count

@torch.inference_mode()
def greedy(model,tok,prompt,max_tokens=32):
    """Python reference; C++ uses its bounded KV cache instead of recomputation."""
    if not tok.instruction or max_tokens<1:raise ValueError('invalid greedy options')
    model.eval();ids=tok.encode_prompt(prompt);result=[]
    for _ in range(max_tokens):
        z=model(torch.tensor([ids]))[0,-1].clone();z[tok.bos_id]=z[tok.response_id]=float('-inf')
        t=int(z.argmax());result.append(t)
        if t==tok.eos_id:return tok.decode(result),result,True
        ids.append(t)
    return tok.decode(result),result,False
