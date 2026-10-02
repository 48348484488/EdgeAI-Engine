#!/usr/bin/env python3
"""Local EdgeAI workbench: evidence search, native model, optional llama-server.

No automatic network/download/install. `search` never calls either model.
`compare` keeps unavailable backends separate from incorrect model answers.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from local_reference import LocalReferenceClient, ReferenceError
ROOT=Path(__file__).resolve().parents[1]


def binary(name: str, build: Path | None = None) -> Path:
    suffix='.exe' if os.name=='nt' else ''
    if build is not None:
        folders=[Path(build),Path(build)/'Release']
    else:
        folders=[ROOT/'build',ROOT/'build/Release',ROOT/'bin/linux-x86_64']
    for folder in folders:
        p=folder/(name+suffix)
        if p.is_file():return p.resolve()
    raise FileNotFoundError(f'{name} not found; build with CMake or pass --build')


def search_code(root: Path, query: str, *, build: Path | None = None, limit: int = 5) -> dict:
    start=time.perf_counter()
    r=subprocess.run([str(binary('edgeai_code_search',build)),str(root),query,'--json','--limit',str(limit)],
                     capture_output=True,timeout=30,shell=False)
    if r.returncode:raise RuntimeError(r.stderr.decode('utf-8','replace')[:2000])
    obj=json.loads(r.stdout);obj['wall_seconds_including_process']=time.perf_counter()-start
    return obj


def file_sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def native_ask(prompt: str, model: Path, *, build: Path | None = None, max_tokens: int = 32) -> dict:
    if not isinstance(prompt,str) or len(prompt.encode('utf-8'))>65536:raise ValueError('prompt limit: 65536 bytes')
    if type(max_tokens) is not int or not 1<=max_tokens<=512:raise ValueError('max_tokens in 1..512')
    model=Path(model).resolve()
    if not model.is_file():raise FileNotFoundError(str(model))
    start=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='edgeai-infer-') as td:
        p=Path(td)/'prompt.bin';o=Path(td)/'answer.bin';p.write_bytes(prompt.encode('utf-8'))
        r=subprocess.run([str(binary('edgeai_generate',build)),str(model),str(p),str(o),str(max_tokens)],
                         capture_output=True,timeout=120,shell=False)
        if r.returncode:raise RuntimeError(r.stderr.decode('utf-8','replace')[:2000])
        metrics=json.loads(r.stdout);raw=o.read_bytes()
    return {'backend':'edge-native','model':model.name,'model_sha256':file_sha256(model),
            'text':raw.decode('utf-8','replace'),'output_hex':raw.hex(),'native_metrics':metrics,
            'wall_seconds':time.perf_counter()-start,'model_loaded_per_prompt':True,'energy_joules':None,
            'max_tokens_requested':max_tokens}


def score_answer(result: dict, expected: str) -> bool:
    if 'error' in result or 'output_hex' not in result:return False
    return result['output_hex']==expected.encode('utf-8').hex()


def validate_cases(cases: list) -> None:
    if not isinstance(cases,list) or not 1<=len(cases)<=500:raise ValueError('1..500 cases required')
    seen=set()
    for row in cases:
        if not isinstance(row,dict) or any(not isinstance(row.get(k),str) or not row[k] for k in ('id','prompt')) or not isinstance(row.get('expected'),str):raise ValueError('case requires id, prompt, expected strings')
        if row['id'] in seen:raise ValueError('duplicate case id')
        if len(row['prompt'].encode())>65536 or len(row['expected'].encode())>65536:raise ValueError('case too large')
        seen.add(row['id'])


def compare(cases: list, model: Path, *, build: Path | None = None, reference_url: str | None = None,
            reference_model: str | None = None, max_tokens: int = 32) -> dict:
    validate_cases(cases)
    # A failed native call aborts rather than producing invented model accuracy.
    rows=[]
    for case in cases:
        answer=native_ask(case['prompt'],model,build=build,max_tokens=max_tokens)
        rows.append({'id':case['id'],'prompt':case['prompt'],'expected':case['expected'],
                     'native':answer,'native_correct':score_answer(answer,case['expected'])})
    native_correct=sum(r['native_correct'] for r in rows)
    external={'status':'not_requested','accuracy':None,'correct':None,'evaluated':0}
    if reference_url is not None:
        client=LocalReferenceClient(reference_url,timeout=30)
        try:
            # Resolve model once to ensure all requests target the same server model.
            if reference_model is None:
                ids=client.model_ids()
                if len(ids)!=1:raise ReferenceError('choose --reference-model when server exposes multiple models')
                reference_model=ids[0]
            for row in rows:
                r=client.ask(row['prompt'],model=reference_model,max_tokens=max_tokens)
                r['output_hex']=r['text'].encode('utf-8').hex()
                row['reference']=r;row['reference_correct']=score_answer(r,row['expected'])
            correct=sum(r['reference_correct'] for r in rows)
            external={'status':'executed','accuracy':correct/len(rows),'correct':correct,'evaluated':len(rows),'model':reference_model}
        except ReferenceError as exc:
            external={'status':'unavailable','accuracy':None,'correct':None,
                      'evaluated':sum('reference' in r for r in rows),'error':str(exc)}
    return {'schema':1,'cases_sha256':hashlib.sha256(json.dumps(cases,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
            'scoring':'exact UTF-8 bytes; no trimming; synthetic diagnostic, not general intelligence',
            'native':{'status':'executed','correct':native_correct,'evaluated':len(rows),'accuracy':native_correct/len(rows)},
            'reference':external,'rows':rows,'energy_joules':None,
            'limits':['different pretraining and parameter budgets; not an architecture ablation',
                      'different tokenizers; equal token limits do not imply equal work',
                      'native reloads each prompt; reference server already running; wall latencies are not equivalent inference costs']}


def write_json(path: Path, obj: dict) -> None:
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(obj,f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
    s=sub.add_parser('search');s.add_argument('root',type=Path);s.add_argument('query');s.add_argument('--limit',type=int,default=5);s.add_argument('--build',type=Path)
    a=sub.add_parser('ask');a.add_argument('prompt');a.add_argument('--backend',choices=['edge','reference'],default='edge');a.add_argument('--model',default=str(ROOT/'models/instructions_v07/default.edge'));a.add_argument('--reference-model');a.add_argument('--server',default='http://127.0.0.1:8080/v1');a.add_argument('--build',type=Path);a.add_argument('--max-tokens',type=int,default=32)
    c=sub.add_parser('compare');c.add_argument('--cases',type=Path,default=ROOT/'data/reference_diagnostic/cases.json');c.add_argument('--model',type=Path,default=ROOT/'models/instructions_v07/default.edge');c.add_argument('--reference-url');c.add_argument('--reference-model');c.add_argument('--build',type=Path);c.add_argument('--max-tokens',type=int,default=32);c.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.cmd=='search':result=search_code(args.root,args.query,build=args.build,limit=args.limit)
        elif args.cmd=='ask':
            result=(native_ask(args.prompt,Path(args.model),build=args.build,max_tokens=args.max_tokens) if args.backend=='edge' else LocalReferenceClient(args.server).ask(args.prompt,model=args.reference_model,max_tokens=args.max_tokens))
        else:
            result=compare(json.loads(args.cases.read_text(encoding='utf-8')),args.model,build=args.build,reference_url=args.reference_url,reference_model=args.reference_model,max_tokens=args.max_tokens);write_json(args.out,result)
            print(json.dumps({'native':result['native'],'reference':result['reference'],'report':str(args.out)},ensure_ascii=False,indent=2))
            return 2 if result['reference']['status']=='unavailable' else 0
        print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False));return 0
    except (ValueError,OSError,RuntimeError,subprocess.TimeoutExpired) as exc:
        print(f'Error: {exc}',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
