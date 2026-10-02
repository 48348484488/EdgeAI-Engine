#!/usr/bin/env python3
"""CPU-budget byte vs byte-BPE trial on a frozen independent source snapshot.

Canonical-token NLL per original byte; not exact marginal string probability,
not task accuracy. Data/tokenizer/parameter tradeoffs are explicit in the report.
"""
import argparse,copy,hashlib,json,math,os,platform,random,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import torch
from torch.nn import functional as F
from byte_bpe import ByteBPE
from external_data import load_snapshot,read_blocks,sha
from transformer_model import TinyTransformer,export_transformer
CONFIGS={'byte257':dict(dim=64,hidden=168,window=64,precision='int8',vocab_size=257),
         'bpe513':dict(dim=48,hidden=128,window=64,precision='int8',vocab_size=513)}

def save(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');os.replace(tmp,path)

def encoded_blocks(raws,tok):return [tok.encode(raw,True) for raw in raws]

@torch.inference_mode()
def evaluate(model,raws,tok,batch_size=16):
    model.eval();encoded=encoded_blocks(raws,tok);nll=0.;correct=targets=0
    for i in range(0,len(encoded),batch_size):
        chunk=encoded[i:i+batch_size];length=max(len(ids)-1 for ids in chunk)
        x=torch.full((len(chunk),length),tok.bos_id,dtype=torch.long);y=torch.full_like(x,-100)
        for j,ids in enumerate(chunk):x[j,:len(ids)-1]=torch.tensor(ids[:-1]);y[j,:len(ids)-1]=torch.tensor(ids[1:])
        z=model(x);loss=F.cross_entropy(z.flatten(0,1),y.flatten(),ignore_index=-100,reduction='sum')
        if not torch.isfinite(loss):raise RuntimeError('nonfinite evaluation')
        nll+=loss.item();mask=y!=-100;correct+=int(((z.argmax(-1)==y)&mask).sum());targets+=int(mask.sum())
    raw_bytes=sum(map(len,raws))
    return dict(bits_per_byte=nll/(raw_bytes*math.log(2)),nll_sum=nll,raw_bytes=raw_bytes,target_tokens=targets,token_accuracy=correct/targets)

def sample_batch(encoded,weights,tok,rng,batch=8,seq=64):
    selected=rng.choices(range(len(encoded)),weights=weights,k=batch);x=[];y=[]
    for j in selected:
        row=encoded[j]
        if len(row)<seq:raise ValueError('training document too short')
        offset=rng.randrange(len(row)-seq+1);target=row[offset:offset+seq]
        x.append([tok.bos_id]+target[:-1]);y.append(target)
    return torch.tensor(x,dtype=torch.long),torch.tensor(y,dtype=torch.long)

def identity(kind,seed,cpu,threads,manifest,tok):
    files=['benchmarks/tokenization_v06.py','tools/transformer_model.py','tools/byte_bpe.py','tools/mixed_model.py','tools/external_data.py','tools/hybrid_model.py','tools/train_tiny.py']
    return dict(protocol='v06-cpu-tokenization-1',kind=kind,seed=seed,cpu_budget=cpu,threads=threads,config=CONFIGS[kind],
                snapshot_sha256=sha(manifest.read_bytes()),tokenizer=tok.fingerprint(),torch=str(torch.__version__),
                host={'platform':platform.platform(),'python':sys.version,'cpu':next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'unknown') if Path('/proc/cpuinfo').exists() else platform.processor()},
                code={p:sha((ROOT/p).read_bytes()) for p in files})

def cached_ok(row,key):
    if row.get('identity')!=key:return False
    artifacts=row.get('artifacts',{})
    if len(artifacts)!=2:return False
    for p,digest in artifacts.items():
        f=(ROOT/p).resolve()
        if not f.is_relative_to(ROOT) or not f.is_file() or sha(f.read_bytes())!=digest:return False
    return True

def bigram(train,test):
    counts=torch.full((256,256),.1,dtype=torch.float64);initial=torch.full((256,),.1,dtype=torch.float64)
    for raw in train:
        ids=torch.tensor(list(raw),dtype=torch.long);initial[ids[0]]+=1
        counts+=torch.bincount(ids[:-1]*256+ids[1:],minlength=65536).reshape(256,256)
    logp=(counts/counts.sum(1,keepdim=True)).log();first=(initial/initial.sum()).log();nll=0
    for raw in test:
        ids=torch.tensor(list(raw),dtype=torch.long);nll-=first[ids[0]].item()+logp[ids[:-1],ids[1:]].sum().item()
    return {'bits_per_byte':nll/(sum(map(len,test))*math.log(2)),'method':'byte bigram add-0.1; first-byte distribution trained; reset per raw block'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cpu-seconds',type=float,default=20);p.add_argument('--seeds',type=int,nargs='+',default=[11,22,33]);p.add_argument('--threads',type=int,default=1);p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--out',type=Path,default=ROOT/'results/v06/training.json');p.add_argument('--model-dir',type=Path,default=ROOT/'models/external_v06');p.add_argument('--resume',action='store_true');a=p.parse_args()
    if not 0<a.cpu_seconds<=3600 or not 1<=a.threads<=64 or len(set(a.seeds))!=len(a.seeds):p.error('invalid CPU budget/threads/seeds')
    torch.set_num_threads(a.threads);torch.use_deterministic_algorithms(True);root=ROOT/'data/cpython_snapshot';manifest=load_snapshot(root)
    whole=time.perf_counter();prep=time.process_time();train=[(root/r['path']).read_bytes() for r in manifest['documents'] if r['split']=='train'];weights=[len(x) for x in train]
    valid=read_blocks(root/'valid.rawblocks');test=read_blocks(root/'test.rawblocks')
    toks={k:ByteBPE.load(root/f'tokenizers/{k}.json') for k in CONFIGS};encoded={k:[toks[k].encode(raw) for raw in train] for k in CONFIGS}
    preparation_cpu=time.process_time()-prep
    a.model_dir.mkdir(parents=True,exist_ok=True);a.out.parent.mkdir(parents=True,exist_ok=True)
    old={}
    if a.resume and a.out.exists():
        prev=json.loads(a.out.read_text());old={(r['kind'],r['seed']):r for r in prev.get('runs',[])}
    report=dict(protocol='same training process-CPU seconds; excludes initialization/evaluation/export/tokenization; includes batch sampling, gradient and optimizer work',
        config=CONFIGS,cpu_budget_seconds=a.cpu_seconds,threads=a.threads,seeds=a.seeds,expected=2*len(a.seeds),runs=[],
        dataset_manifest_sha256=sha((root/'manifest.json').read_bytes()),pretokenization_cpu_seconds=preparation_cpu,
        train_raw_bytes=sum(weights),test_raw_bytes=sum(map(len,test)),valid_raw_bytes=sum(map(len,valid)),
        hardware={'platform':platform.platform(),'processor':platform.processor(),'cpu_model':next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),'unknown') if Path('/proc/cpuinfo').exists() else 'unknown'},
        baseline_bigram=bigram(train,test),metric_caveats=['canonical token sequence code length, not marginalized probability of raw strings','BPE sees more bytes per 64-token window and per batch','different hidden dimensions to match parameter counts','one independently authored project, not independent repositories or multiple natural languages'])
    warm=TinyTransformer(dim=8,hidden=12,vocab_size=257);F.cross_entropy(warm(torch.zeros(1,4,dtype=torch.long)).flatten(0,1),torch.zeros(4,dtype=torch.long)).backward();del warm
    for seed in a.seeds:
        kinds=list(CONFIGS);random.Random(600+seed).shuffle(kinds)
        for kind in kinds:
            tok=toks[kind];key=identity(kind,seed,a.cpu_seconds,a.threads,root/'manifest.json',tok)
            if (kind,seed) in old and cached_ok(old[kind,seed],key):
                row=old[kind,seed];report['runs'].append(row);print(f'{kind} seed {seed}: verified existing artifacts',flush=True);save(a.out,report);continue
            trial=time.perf_counter();torch.manual_seed(seed);model=TinyTransformer(**CONFIGS[kind]);optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.01)
            rng=random.Random(6100+seed);cpu=wall=0.;step=0;threshold=1;best=float('inf');best_state=None;best_step=0;curve=[];token_bytes=[len(p) for p in tok.vocab]+[0];seenbytes=0;digest=hashlib.sha256()
            while cpu<a.cpu_seconds and step<100000:
                model.train();c=time.process_time();w=time.perf_counter();x,y=sample_batch(encoded[kind],weights,tok,rng)
                optimizer.zero_grad(set_to_none=True);z=model(x);loss=F.cross_entropy(z.flatten(0,1),y.flatten())
                if not torch.isfinite(loss):raise RuntimeError('nonfinite training loss')
                loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
                # Count/hashes included in charged CPU budget, not hidden work.
                digest.update(y.numpy().tobytes());seenbytes+=sum(token_bytes[j] for j in y.flatten().tolist())
                cpu+=time.process_time()-c;wall+=time.perf_counter()-w;step+=1
                if cpu>=a.cpu_seconds*threshold/4 or cpu>=a.cpu_seconds:
                    metric=evaluate(model,valid,tok);score=metric['bits_per_byte'];curve.append(dict(step=step,cpu_seconds=cpu,validation_bpb=score))
                    if score<best:best=score;best_state=copy.deepcopy(model.state_dict());best_step=step
                    threshold+=1
            if best_state is None:raise RuntimeError('no validation checkpoint')
            model.load_state_dict(best_state);model.eval();metrics=evaluate(model,test,tok)
            path=a.model_dir/f'{kind}-seed{seed}.edge';pt=path.with_suffix('.pt');export_transformer(model,path,max_generate=128,tokenizer=tok)
            torch.save(dict(kind=kind,config=model.export_config(),state_dict=best_state,tokenizer=tok.payload(),seed=seed,selected_step=best_step,identity=key),pt)
            native=json.loads(subprocess.check_output([str((a.build/'edgeai_text_eval').resolve()),str(path),str(root/'test.rawblocks')],text=True))
            if native['raw_bytes']!=metrics['raw_bytes'] or native['target_tokens']!=metrics['target_tokens'] or abs(native['bits_per_byte']-metrics['bits_per_byte'])>4e-5:raise AssertionError('native NLL mismatch')
            row=dict(kind=kind,seed=seed,identity=key,parameters=sum(p.numel() for p in model.parameters()),steps=step,selected_step=best_step,selected_validation_bpb=best,train_cpu_seconds=cpu,train_wall_seconds=wall,total_trial_wall_seconds=time.perf_counter()-trial,
                training_tokens=step*512,training_raw_bytes=seenbytes,training_batches_sha256=digest.hexdigest(),metrics=metrics,native_metrics=native,validation_curve=curve,model_path=str(path.relative_to(ROOT)),file_bytes=path.stat().st_size,
                artifacts={str(f.relative_to(ROOT)):sha(f.read_bytes()) for f in (path,pt)})
            report['runs'].append(row);report['completed']=len(report['runs']);save(a.out,report)
            print(json.dumps({k:row[k] for k in ('kind','seed','parameters','steps','train_cpu_seconds','metrics','file_bytes')}),flush=True)
    report['completed']=len(report['runs']);report['invocation_wall_seconds']=time.perf_counter()-whole;save(a.out,report)
if __name__=='__main__':main()
