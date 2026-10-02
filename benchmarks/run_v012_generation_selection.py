#!/usr/bin/env python3
"""Targeted seed-33 v0.12 checkpoint-selection ablation.

Replays the published two-block equal-update stream. Checkpoints are selected
only with validation greedy generation; held-out test splits stay untouched
until the selected checkpoint is exported.
"""
import copy,hashlib,json,random,sys,time
from pathlib import Path
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'benchmarks'))
from instruction_data import load_dataset,sha
from sft_model import expand_checkpoint,make_batch,response_loss,validation_loss,greedy
from transformer_model import export_transformer
from instruction_blocks_v012 import promote_blocks,repo_path
from instruction_blocks_equal_steps_v012 import baseline_plan,target_steps
from instruction_blocks_generation_select_v012 import (select_checkpoint,validation_generation,build_identity,assert_fair_pair)

SEED=33

def main():
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    data_dir=ROOT/'data/instructions_v07';data,_=load_dataset(data_dir)
    baseline_path=ROOT/'results/v012/training.json';baseline=json.loads(baseline_path.read_text())
    plan=baseline_plan(baseline,SEED)
    if plan['target_steps']!=target_steps(SEED): raise ValueError('published seed33 step count changed')
    base_path=ROOT/'models/external_v06/bpe513-seed33.pt'
    if sha(base_path.read_bytes())!=plan['source_checkpoint_sha256']: raise ValueError('source checkpoint changed')
    cp=torch.load(base_path,map_location='cpu',weights_only=True)
    base,tok=expand_checkpoint(cp,SEED);model=promote_blocks(base,2,SEED)
    dataset_digest=sha((data_dir/'manifest.json').read_bytes())
    config=model.export_config()
    identity_one=build_identity(SEED,1,plan['target_steps'],1,dataset_digest,tok.fingerprint(),config)
    identity_two=build_identity(SEED,2,plan['target_steps'],1,dataset_digest,tok.fingerprint(),config)
    fairness_verified=assert_fair_pair(identity_one,identity_two)
    groups={}
    for row in data['train']: groups.setdefault(row['task'],[]).append(row)
    rng=random.Random(7700+SEED);tasks=sorted(groups);opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    marks=set(plan['validation_steps']);candidates=[];selected_state=None;selected_row=None
    digest=hashlib.sha256();seen={task:0 for task in tasks};cpu=0.;wall=0.
    for step in range(1,plan['target_steps']+1):
        model.train();c0=time.process_time();w0=time.perf_counter();batch=[]
        for _ in range(16):
            task=rng.choice(tasks);row=rng.choice(groups[task]);batch.append(row)
            seen[task]+=1;digest.update(row['id'].encode())
        x,y=make_batch(batch,tok);opt.zero_grad(set_to_none=True);loss=response_loss(model(x),y)
        if not torch.isfinite(loss): raise RuntimeError('nonfinite loss')
        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);opt.step()
        cpu+=time.process_time()-c0;wall+=time.perf_counter()-w0
        if step in marks:
            nll=validation_loss(model,data['valid'],tok);gm=validation_generation(model,tok,data['valid'])
            row=dict(step=step,validation_nll=nll,greedy_correct=gm['correct'],greedy_exact=gm['exact'],greedy_eos=gm['eos'])
            candidates.append(row)
            winner=select_checkpoint(candidates)
            if winner['step']==step:
                selected_state=copy.deepcopy(model.state_dict());selected_row=dict(row)
            print(json.dumps(row),flush=True)
    if digest.hexdigest()!=plan['batch_ids_sha256'] or seen!=plan['examples_seen']:
        raise RuntimeError('selection ablation changed training exposure')
    if selected_state is None: raise RuntimeError('no checkpoint selected')
    model.load_state_dict(selected_state);model.eval()
    model_dir=repo_path(ROOT/'models/v012_generation_selection');model_dir.mkdir(parents=True,exist_ok=True)
    edge=model_dir/'seed33-b2-generation-selected.edge';export_transformer(model,edge,tokenizer=tok,max_generate=32)
    rel=str(edge.relative_to(ROOT))
    run=dict(seed=SEED,blocks=2,steps=plan['target_steps'],selected_step=selected_row['step'],
             selected_validation_nll=selected_row['validation_nll'],validation_selection=selected_row,
             validation_candidates=candidates,train_cpu_seconds=cpu,train_wall_seconds=wall,
             after_path=rel,artifacts={rel:sha(edge.read_bytes())},parameters=sum(p.numel() for p in model.parameters()),
             file_bytes=edge.stat().st_size,batch_ids_sha256=digest.hexdigest(),examples_seen=seen,
             fairness_identity_one=identity_one,fairness_identity_two=identity_two)
    report=dict(protocol='seed33 two-block equal-update replay; checkpoint selected by validation greedy correct/exact then NLL',
                expected=1,completed=1,architectures=[1,2],fairness_verified=fairness_verified,dataset_sha256=dataset_digest,runs=[run])
    out=repo_path(ROOT/'results/v012_generation_selection/training.json');out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(selected=selected_row,out=str(out))),flush=True)

if __name__=='__main__': main()
