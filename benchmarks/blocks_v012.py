#!/usr/bin/env python3
"""Controlled EdgeAI experiment: one Transformer block versus two.

Both arms start from the same expanded v0.6 checkpoint. The second block in the
2-block arm is initialized as an exact residual identity, so both arms produce
the same logits before optimization. Training uses the same frozen v0.7
instruction dataset, one CPU thread, identical sampler seed, optimizer and
response-only objective. Each arm gets the same process-CPU optimization budget.

This is a structural capacity experiment, not a general-intelligence benchmark.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, math, os, platform, random, statistics, sys, time
from pathlib import Path
import torch
from torch import nn
from torch.nn import functional as F

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import load_dataset, sha
from sft_model import expand_checkpoint, make_batch, response_loss, validation_loss
from mixed_model import replace_linear

NAMES=('query','key','value','project','up','down')

class TransformerBlock(nn.Module):
    def __init__(self, dim:int, hidden:int, window:int, precision:str, rope_base:float):
        super().__init__()
        self.dim,self.hidden,self.window,self.precision,self.rope_base=dim,hidden,window,precision,rope_base
        self.query,self.key,self.value,self.project=(nn.Linear(dim,dim) for _ in range(4))
        self.up,self.down=nn.Linear(dim,hidden),nn.Linear(hidden,dim)
        for name in NAMES:setattr(self,name,replace_linear(getattr(self,name),precision))
        self.register_buffer('inv_freq',torch.tensor([rope_base**(-2*j/dim) for j in range(dim//2)],dtype=torch.float32),persistent=False)
    def rotate(self,x):
        angles=torch.arange(x.shape[1],device=x.device,dtype=x.dtype)[:,None]*self.inv_freq
        c,s=angles.cos()[None],angles.sin()[None]
        a,b=x[...,0::2],x[...,1::2]
        return torch.stack((a*c-b*s,a*s+b*c),-1).flatten(-2)
    def forward(self,e):
        n=F.layer_norm(e,(self.dim,),eps=1e-5)
        q,k=self.rotate(self.query(n)),self.rotate(self.key(n));v=self.value(n)
        t=torch.arange(e.shape[1],device=e.device);distance=t[:,None]-t[None,:]
        scores=q@k.transpose(-1,-2)/math.sqrt(self.dim)
        weights=scores.masked_fill((distance<0)|(distance>=self.window),float('-inf')).softmax(-1)
        h=e+self.project(weights@v)
        h=h+.5*self.down(F.silu(self.up(F.layer_norm(h,(self.dim,),eps=1e-5))))
        return h

class StackedTransformer(nn.Module):
    def __init__(self,config:dict,blocks:int):
        super().__init__()
        if blocks not in (1,2):raise ValueError('only 1 or 2 blocks supported by this experiment')
        self.config=dict(config);self.vocab_size=config['vocab_size'];self.dim=config['dim']
        self.emb=nn.Embedding(self.vocab_size,self.dim)
        self.blocks=nn.ModuleList([TransformerBlock(config['dim'],config['hidden'],config['window'],config['precision'],config['rope_base']) for _ in range(blocks)])
        self.out=replace_linear(nn.Linear(self.dim,self.vocab_size),config['precision'])
    def forward(self,tokens):
        if tokens.ndim!=2 or tokens.shape[1]==0 or tokens.shape[1]>16384:raise ValueError('expected nonempty [batch,sequence<=16384] tokens')
        h=self.emb(tokens)
        for block in self.blocks:h=block(h)
        return self.out(F.layer_norm(h,(self.dim,),eps=1e-5))

def copy_one_block(base,blocks:int,seed:int):
    cfg=base.export_config();torch.manual_seed(seed+19000+blocks)
    model=StackedTransformer(cfg,blocks)
    model.emb.load_state_dict(base.emb.state_dict());model.out.load_state_dict(base.out.state_dict())
    for name in NAMES:getattr(model.blocks[0],name).load_state_dict(getattr(base,name).state_dict())
    if blocks==2:
        with torch.no_grad():
            for name in ('project','down'):
                layer=getattr(model.blocks[1],name);layer.weight.zero_()
                if layer.bias is not None:layer.bias.zero_()
    return model

@torch.inference_mode()
def parity(base,one,two,tok):
    prompts=['Copy exactly: abc','Some: 3 + 4','Expressao para x * 2:']
    diffs=[]
    for prompt in prompts:
        ids=torch.tensor([tok.encode_prompt(prompt)])
        z=base(ids)
        diffs.extend([(z-one(ids)).abs().max().item(),(z-two(ids)).abs().max().item()])
    return max(diffs)

@torch.inference_mode()
def teacher_forced_metrics(model,rows,tok,batch_size=32):
    model.eval();correct=total=exact_rows=0
    for i in range(0,len(rows),batch_size):
        x,y=make_batch(rows[i:i+batch_size],tok);pred=model(x).argmax(-1);mask=y!=-100
        correct+=int(((pred==y)&mask).sum());total+=int(mask.sum())
        for j in range(y.shape[0]):
            m=mask[j];exact_rows+=int(bool(torch.all(pred[j][m]==y[j][m])))
    return dict(rows=len(rows),exact_rows=exact_rows,target_tokens=total,correct_tokens=correct,token_accuracy=(correct/total if total else None))

def train_arm(base,tok,train,valid,groups,blocks,seed,cpu_seconds):
    model=copy_one_block(base,blocks,seed)
    opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    rng=random.Random(880000+seed)
    tasks=sorted(groups);step=0;train_cpu=0.;wall=0.;threshold=1;curve=[];best=float('inf');best_state=None;best_step=0
    digest=hashlib.sha256();seen={t:0 for t in tasks};validation_cpu=0.
    while train_cpu<cpu_seconds and step<100000:
        model.train();c=time.process_time();w=time.perf_counter();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);row=rng.choice(groups[task]);batch.append(row);seen[task]+=1;digest.update(row['id'].encode())
        x,y=make_batch(batch,tok);opt.zero_grad(set_to_none=True);loss=response_loss(model(x),y)
        if not torch.isfinite(loss):raise RuntimeError('nonfinite training loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);opt.step()
        train_cpu+=time.process_time()-c;wall+=time.perf_counter()-w;step+=1
        if train_cpu>=cpu_seconds*threshold/4 or train_cpu>=cpu_seconds:
            c=time.process_time();metric=validation_loss(model,valid,tok)
            validation_cpu+=time.process_time()-c
            curve.append(dict(step=step,train_cpu_seconds=train_cpu,validation_nll=metric))
            if metric<best:best=metric;best_state=copy.deepcopy(model.state_dict());best_step=step
            threshold+=1
    if best_state is None:raise RuntimeError('no selected checkpoint')
    model.load_state_dict(best_state);model.eval()
    return model,dict(blocks=blocks,seed=seed,parameters=sum(p.numel() for p in model.parameters()),steps=step,selected_step=best_step,
                      train_cpu_seconds=train_cpu,train_wall_seconds=wall,validation_cpu_seconds=validation_cpu,
                      selected_validation_nll=best,validation_curve=curve,batch_ids_sha256=digest.hexdigest(),examples_seen=seen)

def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n');os.replace(tmp,path)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cpu-seconds',type=float,default=12.0);p.add_argument('--seeds',type=int,nargs='+',default=[11,22,33]);p.add_argument('--threads',type=int,default=1)
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07');p.add_argument('--out',type=Path,default=ROOT/'results/v012/blocks.json');a=p.parse_args()
    if not 0<a.cpu_seconds<=3600 or not 1<=a.threads<=64 or not a.seeds or len(set(a.seeds))!=len(a.seeds):p.error('invalid budget')
    torch.set_num_threads(a.threads);torch.use_deterministic_algorithms(True)
    data,manifest=load_dataset(a.data);train,valid=data['train'],data['valid'];groups={}
    for r in train:groups.setdefault(r['task'],[]).append(r)
    tests=[]
    for split in ('test_id','test_template','test_range','test_family'):
        tests.extend([dict(r,split=split) for r in data[split]])
    for seed in a.seeds:
        cp=torch.load(ROOT/f'models/external_v06/bpe513-seed{seed}.pt',map_location='cpu',weights_only=True);base,tok=expand_checkpoint(cp,seed)
        for rows in (train,valid):
            for i in range(0,len(rows),16):make_batch(rows[i:i+16],tok)
    report=dict(protocol='edge-blocks-v012-1',description='1 vs 2 Transformer blocks, same starting function/data/optimizer/sampler/process-CPU budget',
                cpu_budget_seconds_per_arm_seed=a.cpu_seconds,seeds=a.seeds,threads=a.threads,dataset_sha256=sha((a.data/'manifest.json').read_bytes()),
                evaluation='all 194 held-out rows: response NLL plus teacher-forced target-token and exact-row accuracy; no autoregressive generation score',
                platform=platform.platform(),python=sys.version,torch=str(torch.__version__),runs=[],synthetic=True,energy_joules=None)
    started=time.perf_counter()
    for seed in a.seeds:
        cp=torch.load(ROOT/f'models/external_v06/bpe513-seed{seed}.pt',map_location='cpu',weights_only=True);base,tok=expand_checkpoint(cp,seed);base.eval()
        one0=copy_one_block(base,1,seed).eval();two0=copy_one_block(base,2,seed).eval();d=parity(base,one0,two0,tok)
        if d>1e-6:raise RuntimeError(f'initial parity failed seed={seed} max_abs={d}')
        for blocks in (1,2):
            model,row=train_arm(base,tok,train,valid,groups,blocks,seed,a.cpu_seconds)
            test_nll=validation_loss(model,tests,tok)
            tf=teacher_forced_metrics(model,tests,tok)
            row['initial_max_abs_diff']=d;row['full_test_response_nll']=test_nll;row['teacher_forced']=tf
            row['by_split_teacher_forced']={sp:teacher_forced_metrics(model,[r for r in tests if r['split']==sp],tok) for sp in ('test_id','test_template','test_range','test_family')}
            report['runs'].append(row);save(a.out,report)
            print(json.dumps({k:row[k] for k in ('seed','blocks','parameters','steps','selected_validation_nll','full_test_response_nll','teacher_forced')}),flush=True)
    def agg(blocks):
        rs=[r for r in report['runs'] if r['blocks']==blocks];params=sorted({r['parameters'] for r in rs})
        if len(params)!=1:raise RuntimeError('parameter count changed inside one arm')
        exact=sum(r['teacher_forced']['exact_rows'] for r in rs);rows=sum(r['teacher_forced']['rows'] for r in rs)
        correct=sum(r['teacher_forced']['correct_tokens'] for r in rs);targets=sum(r['teacher_forced']['target_tokens'] for r in rs)
        return dict(runs=len(rs),parameters=params[0],median_steps=statistics.median(r['steps'] for r in rs),
                    median_validation_nll=statistics.median(r['selected_validation_nll'] for r in rs),median_full_test_nll=statistics.median(r['full_test_response_nll'] for r in rs),
                    teacher_forced_exact_rows=exact,teacher_forced_rows=rows,teacher_forced_exact_rate=exact/rows,
                    teacher_forced_correct_tokens=correct,teacher_forced_target_tokens=targets,teacher_forced_token_accuracy=correct/targets,
                    total_train_cpu_seconds=sum(r['train_cpu_seconds'] for r in rs),initial_max_abs_diff=max(r['initial_max_abs_diff'] for r in rs))
    report['aggregate']={'1block':agg(1),'2block':agg(2)}
    report['by_split_aggregate']={}
    for sp in ('test_id','test_template','test_range','test_family'):
        report['by_split_aggregate'][sp]={}
        for blocks in (1,2):
            ms=[r['by_split_teacher_forced'][sp] for r in report['runs'] if r['blocks']==blocks]
            exact=sum(m['exact_rows'] for m in ms);rows=sum(m['rows'] for m in ms);correct=sum(m['correct_tokens'] for m in ms);targets=sum(m['target_tokens'] for m in ms)
            report['by_split_aggregate'][sp][f'{blocks}block']=dict(rows=rows,exact_rows=exact,exact_rate=exact/rows,correct_tokens=correct,target_tokens=targets,token_accuracy=correct/targets)
    report['completed']=len(report['runs']);report['wall_seconds']=time.perf_counter()-started
    save(a.out,report);print(json.dumps(report['aggregate'],indent=2),flush=True)

if __name__=='__main__':main()
