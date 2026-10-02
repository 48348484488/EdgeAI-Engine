#!/usr/bin/env python3
"""Execute local milestones without interactive prompts. No installs or network.

Quick is a smoke test; research runs 15 fixed-update and 6 CPU-budget trials.
Status is persisted after each stage; errors stop with log location. Completed
training trials are reused only when identities AND model hashes still match.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def stage_commands(profile,build,threads):
    if profile == "indexed":
        from goals_v010 import stage_commands as indexed_stages
        return indexed_stages(profile,build,threads)
    if profile == "useful":
        from goals_v09 import stage_commands as useful_stages
        return useful_stages(profile,build,threads)
    if profile in ('instructions','instructions-quick'):
        from goals_v07 import stage_commands as instruction_stages
        return instruction_stages(profile,build,threads)
    if profile in ('independent','independent-quick'):
        from goals_v06 import stage_commands as independent_stages
        return independent_stages(profile,build,threads)
    if profile not in ('quick','research') or threads<1:raise ValueError('invalid profile/threads')
    py=sys.executable;build=Path(build).resolve();quick=profile=='quick'
    report=ROOT/('results/v05/quick/language.json' if quick else 'results/v05/language.json')
    modeldir=ROOT/('models/quick_v05' if quick else 'models/language_v05')
    train=[py,str(ROOT/'benchmarks/language_v05.py'),'--steps','30' if quick else '400','--seeds']+(['11'] if quick else ['11','22','33'])
    if quick:train+=['--variants','hybrid_int8','transformer_int8']
    train+=['--threads',str(threads),'--build',str(build),'--out',str(report),'--model-dir',str(modeldir),'--resume']
    stages = [
        ('configure',['cmake','-S',str(ROOT),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release']),
        ('build',['cmake','--build',str(build),'--config','Release','-j','2']),
        ('cpp_tests',['ctest','--test-dir',str(build),'-C','Release','--output-on-failure']),
        ('python_tests',[py,'-m','unittest','discover','-s',str(ROOT/'tests'),'-p','test_*.py','-v']),
        ('transformer_parity',[py,str(ROOT/'tools/verify_language.py'),'--build',str(build),'--out',str(ROOT/f'results/v05/parity-{profile}.json')]),
        ('train_and_evaluate',train),
        ('trained_parity',[py,str(ROOT/'tools/verify_trained.py'),'--build',str(build),'--report',str(report),'--out',str(report.parent/'trained_parity.json')]),
        ('native_benchmark',[py,str(ROOT/'benchmarks/native_v05.py'),'--build',str(build),'--report',str(report),'--repeats','2' if quick else '5','--tokens','2000' if quick else '10000','--out',str(report.parent/'native.json')]),
    ]

    if not quick:
        budget_report=ROOT/'results/v05/compute_budget.json'
        stages += [
            ('equal_cpu_training',[py,str(ROOT/'benchmarks/compute_budget_v05.py'),'--cpu-seconds','12','--seeds','11','22','33','--build',str(build),'--out',str(budget_report)]),
            ('equal_cpu_parity',[py,str(ROOT/'tools/verify_trained.py'),'--build',str(build),'--report',str(budget_report),'--out',str(ROOT/'results/v05/compute_trained_parity.json')]),
            ('equal_cpu_native',[py,str(ROOT/'benchmarks/native_v05.py'),'--build',str(build),'--report',str(budget_report),'--out',str(ROOT/'results/v05/native_compute.json')]),
            ('energy_probe',[py,str(ROOT/'benchmarks/measure_energy.py'),'--out',str(ROOT/'results/v05/energy.json'),'--',str(build/'edgeai_runtime_benchmark'),str(ROOT/'models/compute_v05/transformer_int8-seed11.edge'),'100000']),
        ]
    return stages

def save(path,state):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2)+'\n');os.replace(tmp,path)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',choices=['indexed','useful','quick','research','independent','independent-quick','instructions','instructions-quick'],default='instructions-quick');p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--threads',type=int,default=1);p.add_argument('--list',action='store_true');a=p.parse_args()
    if not 1<=a.threads<=256:p.error('threads in 1..256')
    # Until multi-config executable resolution is tested, avoid silent Windows failure.
    if os.name=='nt':p.error('this orchestration script is validated on Linux; use build_windows.bat for the C++ engine')
    stages=stage_commands(a.profile,a.build,a.threads)
    if a.list:
        print(json.dumps([{'stage':n,'command':c} for n,c in stages],indent=2));return
    if a.profile in ('useful','indexed'):
        pass
    elif a.profile.startswith('instructions'):
        from instruction_data import load_dataset
        load_dataset(ROOT/'data/instructions_v07')
    elif a.profile.startswith('independent'):
        from external_data import load_snapshot
        load_snapshot(ROOT/'data/cpython_snapshot')
    else:
        from language_data import load_manifest
        load_manifest(ROOT/'data/project_corpus')
    logdir=ROOT/f'results/{"v010" if a.profile=="indexed" else "v09" if a.profile=="useful" else "v07" if a.profile.startswith("instructions") else "v06" if a.profile.startswith("independent") else "v05"}/goals-{a.profile}';logdir.mkdir(parents=True,exist_ok=True)
    path=logdir/'status.json';state=dict(profile=a.profile,started=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='running',stages=[])
    save(path,state)
    for name,cmd in stages:
        log=logdir/(name+'.log');row=dict(name=name,command=cmd,status='running',log=str(log.relative_to(ROOT)));state['stages'].append(row);save(path,state)
        print(f'[{name}] started',flush=True)
        with log.open('w') as f:
            try:result=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,shell=False,env=dict(os.environ,EDGEAI_BUILD_DIR=str(a.build.resolve())))
            except OSError as exc:
                f.write(str(exc)+'\n');row.update(status='failed',error=str(exc));state['status']='failed';save(path,state);raise SystemExit(f'{name} failed: {log}')
        row.update(status='passed' if result.returncode==0 else 'failed',exit_code=result.returncode);save(path,state)
        if result.returncode:
            state['status']='failed';save(path,state);raise SystemExit(f'{name} failed: {log}')
        print(f'[{name}] passed',flush=True)
    state['status']='passed';state['finished']=datetime.datetime.now(datetime.timezone.utc).isoformat();save(path,state)
    print('Metas desta execução concluídas. Status: '+str(path))
if __name__=='__main__':main()
