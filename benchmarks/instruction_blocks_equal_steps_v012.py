#!/usr/bin/env python3
"""Equal-update ablation: give the two-block v0.12 model the exact one-block training stream."""
import argparse,copy,hashlib,json,random,sys,time
from pathlib import Path
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss
from transformer_model import export_transformer,numeric_weight_bytes
from instruction_blocks_v012 import promote_blocks,repo_path

SEEDS=(11,22,33)
ARCHITECTURES=(1,2)
DEFAULT_THREADS=1
FROZEN_ONE_BLOCK_STEPS={11:11269,22:11286,33:9661}

def target_steps(seed):
    try:
        return FROZEN_ONE_BLOCK_STEPS[int(seed)]
    except (KeyError,ValueError,TypeError):
        raise ValueError('published equal-step ablation is pinned to seeds 11/22/33')


_CONTROL_KEYS=('protocol','seed','target_steps','threads','dataset_sha256','tokenizer_fingerprint',
               'dim','hidden','window','precision','batch','lr','weight_decay','clip_norm',
               'max_length','selection')

def build_identity(seed,blocks,target_steps,threads,dataset_sha256,tokenizer_fingerprint,config):
    if blocks not in ARCHITECTURES or target_steps<4: raise ValueError('invalid equal-step identity')
    return dict(protocol='edge-sft-v012-equal-updates-1',seed=int(seed),target_steps=int(target_steps),
                threads=int(threads),dataset_sha256=str(dataset_sha256),
                tokenizer_fingerprint=str(tokenizer_fingerprint),dim=int(config['dim']),
                hidden=int(config['hidden']),window=int(config['window']),precision=str(config['precision']),
                vocab_size=int(config.get('vocab_size',256)),batch=16,lr=.001,weight_decay=.01,
                clip_norm=1.0,max_length=128,
                selection='minimum response validation NLL at the frozen one-block validation steps',
                blocks=int(blocks))

def assert_fair_pair(one,two):
    if one.get('blocks')!=1 or two.get('blocks')!=2: raise ValueError('need blocks 1 and 2')
    missing=[k for k in _CONTROL_KEYS if k not in one or k not in two]
    if missing: raise ValueError('missing equal-update controls: '+','.join(missing))
    changed=[k for k in _CONTROL_KEYS if one[k]!=two[k]]
    if changed: raise ValueError('unfair equal-update pair: '+','.join(changed))
    return True

def baseline_plan(report,seed):
    if report.get('fairness_verified') is not True: raise ValueError('baseline fairness not verified')
    rows=[r for r in report.get('runs',[]) if r.get('seed')==seed and r.get('blocks')==1]
    if len(rows)!=1: raise ValueError('missing unique one-block baseline')
    row=rows[0];marks=[int(x['step']) for x in row.get('validation_curve',[])]
    if not marks or marks[-1]!=int(row['steps']): raise ValueError('invalid baseline validation schedule')
    return dict(seed=seed,target_steps=int(row['steps']),validation_steps=marks,
                batch_ids_sha256=row['batch_ids_sha256'],examples_seen=row['examples_seen'],
                source_checkpoint_sha256=row['source_checkpoint_sha256'],
                selected_step=row['selected_step'],selected_validation_nll=row['selected_validation_nll'],
                train_cpu_seconds=row['train_cpu_seconds'],train_wall_seconds=row['train_wall_seconds'])

def save(path,obj):
    path=repo_path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,indent=2)+'\n')
    tmp.replace(path)

def train(seed,plan,threads,data,groups,dataset_digest,model_dir):
    base_path=ROOT/f'models/external_v06/bpe513-seed{seed}.pt'
    if sha(base_path.read_bytes())!=plan['source_checkpoint_sha256']:
        raise ValueError('baseline source checkpoint changed')
    cp=torch.load(base_path,map_location='cpu',weights_only=True)
    base,tok=expand_checkpoint(cp,seed);model=promote_blocks(base,2,seed)
    config=model.export_config()
    one_identity=build_identity(seed,1,plan['target_steps'],threads,dataset_digest,tok.fingerprint(),config)
    two_identity=build_identity(seed,2,plan['target_steps'],threads,dataset_digest,tok.fingerprint(),config)
    assert_fair_pair(one_identity,two_identity)
    for rows in (data['train'],data['valid']):
        for i in range(0,len(rows),16): make_batch(rows[i:i+16],tok)

    rng=random.Random(7700+seed);tasks=sorted(groups);optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    best=float('inf');best_state=None;best_step=0;curve=[];digest=hashlib.sha256()
    seen={task:0 for task in tasks};marks=set(plan['validation_steps'])
    train_cpu=train_wall=0.0
    for step in range(1,plan['target_steps']+1):
        model.train();c0=time.process_time();w0=time.perf_counter();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);row=rng.choice(groups[task]);batch.append(row)
            seen[task]+=1;digest.update(row['id'].encode())
        x,y=make_batch(batch,tok);optimizer.zero_grad(set_to_none=True);loss=response_loss(model(x),y)
        if not torch.isfinite(loss): raise RuntimeError('nonfinite training loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        train_cpu+=time.process_time()-c0;train_wall+=time.perf_counter()-w0
        if step in marks:
            metric=validation_loss(model,data['valid'],tok)
            curve.append(dict(step=step,validation_nll=metric,train_cpu_seconds=train_cpu))
            if metric<best: best=metric;best_state=copy.deepcopy(model.state_dict());best_step=step
            print(json.dumps(dict(seed=seed,blocks=2,step=step,validation_nll=metric)),flush=True)

    got=digest.hexdigest()
    if got!=plan['batch_ids_sha256']: raise RuntimeError('minibatch stream differs from one-block baseline')
    if seen!=plan['examples_seen']: raise RuntimeError('task exposure differs from one-block baseline')
    if best_state is None: raise RuntimeError('no validation checkpoint')
    model.load_state_dict(best_state);model.eval();model_dir.mkdir(parents=True,exist_ok=True)
    edge=model_dir/f'seed{seed}-b2-equalupdates.edge';pt=edge.with_suffix('.pt')
    export_transformer(model,edge,tokenizer=tok,max_generate=32)
    torch.save(dict(config=model.export_config(),state_dict=best_state,tokenizer=tok.payload(),
                    seed=seed,blocks=2,phase='equal_updates',selected_step=best_step,
                    identity=two_identity),pt)
    return dict(seed=seed,blocks=2,target_steps=plan['target_steps'],steps=plan['target_steps'],
                validation_steps=plan['validation_steps'],selected_step=best_step,
                selected_validation_nll=best,validation_curve=curve,train_cpu_seconds=train_cpu,
                train_wall_seconds=train_wall,parameters=sum(p.numel() for p in model.parameters()),
                file_bytes=edge.stat().st_size,numeric_weight_bytes=numeric_weight_bytes(model),
                batch_ids_sha256=got,examples_seen=seen,model_path=str(edge.relative_to(ROOT)),
                model_sha256=sha(edge.read_bytes()),pt_path=str(pt.relative_to(ROOT)),
                pt_sha256=sha(pt.read_bytes()),baseline_one_selected_step=plan['selected_step'],
                baseline_one_selected_validation_nll=plan['selected_validation_nll'],
                baseline_one_train_cpu_seconds=plan['train_cpu_seconds'],
                baseline_one_train_wall_seconds=plan['train_wall_seconds'],
                fairness_identity_one=one_identity,fairness_identity_two=two_identity)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seeds',type=int,nargs='+',default=list(SEEDS));p.add_argument('--threads',type=int,default=DEFAULT_THREADS)
    p.add_argument('--data',type=Path,default=ROOT/'data/instructions_v07')
    p.add_argument('--baseline',type=Path,default=ROOT/'results/v012/training.json')
    p.add_argument('--model-dir',type=Path,default=ROOT/'models/v012_equalsteps')
    p.add_argument('--out',type=Path,default=ROOT/'results/v012_equal_steps/training.json');a=p.parse_args()
    if tuple(a.seeds)!=SEEDS or a.threads!=1: p.error('published ablation is pinned to seeds 11/22/33 and one thread')
    torch.set_num_threads(a.threads);torch.use_deterministic_algorithms(True)
    baseline=json.loads(a.baseline.read_text());data,_=load_dataset(a.data)
    digest=sha((a.data/'manifest.json').read_bytes())
    if digest!=baseline.get('dataset_sha256'): raise ValueError('dataset differs from frozen baseline')
    groups={}
    for row in data['train']: groups.setdefault(row['task'],[]).append(row)
    model_dir=repo_path(a.model_dir);started=time.perf_counter();runs=[]
    for seed in a.seeds:
        plan=baseline_plan(baseline,seed)
        if plan['target_steps']!=target_steps(seed):
            raise ValueError('frozen one-block step count differs from published v0.12 baseline')
        runs.append(train(seed,plan,a.threads,data,groups,digest,model_dir))
    report=dict(protocol='two-block equal-update ablation against frozen one-block v0.12 baseline',
                seeds=a.seeds,architectures=[1,2],threads=a.threads,expected=3,completed=len(runs),
                dataset_sha256=digest,baseline_training_sha256=sha(a.baseline.read_bytes()),
                fairness_verified=all(assert_fair_pair(r['fairness_identity_one'],r['fairness_identity_two']) for r in runs),
                runs=runs,wall_seconds=time.perf_counter()-started,energy_joules=None)
    save(a.out,report);print(json.dumps(dict(completed=len(runs),fairness_verified=report['fairness_verified'],out=str(a.out))))

if __name__=='__main__': main()
