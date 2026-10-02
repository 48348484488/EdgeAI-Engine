#!/usr/bin/env python3
"""Differential, source-grounded and timed code search; no model/network/training.

Uses the licensed CPython snapshot already distributed, with automatically derived
literal-name queries. This is a lexical regression/performance task, not semantic
code understanding or a blinded human benchmark. Full sessions include process
startup, all queries, strict refresh/read I/O and output. Cold runs contain one query.
"""
from __future__ import annotations
import argparse, ast, hashlib, json, os, platform, random, statistics, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def check_evidence(root,result):
    if result.get('neural_used') or result.get('partial') or 'error' in result:
        raise ValueError('not a complete deterministic result')
    for hit in result['hits']:
        rel=Path(hit['path'])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe citation')
        path=root/rel
        lines=path.read_text(encoding='utf-8').splitlines()
        a,b,m=hit['start_line'],hit['end_line'],hit['match_line']
        if not 1<=a<=m<=b<=len(lines):raise ValueError('invalid citation range')
        if '\n'.join(lines[a-1:b])!=hit['text']:raise ValueError('citation text mismatch')

def make_cases(root):
    cases=[];sources={}
    for path in sorted(root.rglob('*.py')):
        sources[path.relative_to(root).as_posix()]=digest(path)
        tree=ast.parse(path.read_bytes(),filename=str(path))
        nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
        for node in nodes[:2]:
            cases.append(dict(query=f'`{node.name}`',expected_path=path.relative_to(root).as_posix(),expected_line=node.lineno))
    for i in range(8):cases.append(dict(query=f'NoSuchEdgeAIRegressionSymbolV010_{i}',expected_path=None))
    return cases,sources

def invoke(exe,root,queries):
    started=time.perf_counter()
    p=subprocess.run([str(exe),str(root),'--batch','--json'],input='\n'.join(queries)+'\n',text=True,capture_output=True,timeout=120,check=True)
    elapsed=(time.perf_counter()-started)*1000
    rows=[json.loads(s) for s in p.stdout.splitlines()]
    if len(rows)!=len(queries):raise ValueError('wrong response count')
    for r in rows:check_evidence(root,r)
    return elapsed,rows

def measure(build,root,repeats):
    cases,sources=make_cases(root)
    if not cases or all(c['expected_path'] is None for c in cases):raise ValueError('no positive cases')
    queries=[c['query'] for c in cases]
    exes={'v09':build/'edgeai_code_search_v09_baseline','v010':build/'edgeai_code_search'}
    rows={};runs=[];cold=[]
    rng=random.Random(20260925)
    for rep in range(repeats):
        names=list(exes);rng.shuffle(names)
        for name in names:
            ms,result=invoke(exes[name],root,queries)
            runs.append(dict(variant=name,repeat=rep,milliseconds=ms))
            if name in rows and rows[name]!=result:raise ValueError('nondeterministic results')
            rows[name]=result
        rng.shuffle(names)
        for name in names:
            ms,_=invoke(exes[name],root,queries[:1]);cold.append(dict(variant=name,repeat=rep,milliseconds=ms))
    if sources!={p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*.py'))}:raise ValueError('corpus changed during measurement')
    for old,new in zip(rows['v09'],rows['v010']):
        for key in ('hits','scanned_files','scanned_bytes','skipped_files','partial','neural_used','method'):
            if old[key]!=new[key]:raise ValueError(f'baseline mismatch: {key}')
    positive=sum(c['expected_path'] is not None for c in cases);top1=top5=negative=0
    for c,r in zip(cases,rows['v010']):
        if c['expected_path'] is None:negative+=not r['hits'];continue
        matches=[h['path']==c['expected_path'] and h['match_line']==c['expected_line'] for h in r['hits']]
        top1+=bool(matches and matches[0]);top5+=any(matches)
    median={n:statistics.median(r['milliseconds'] for r in runs if r['variant']==n) for n in exes}
    cold_median={n:statistics.median(r['milliseconds'] for r in cold if r['variant']==n) for n in exes}
    return dict(schema=1,task='lexical CPython source search, not model quality',
       sources=sources,cases=cases,results=rows,runs=runs,cold_runs=cold,
       source_files=len(sources),positive_cases=positive,negative_cases=len(cases)-positive,
       top1=top1,top5=top5,correct_empty=negative,differential_cases=len(cases),
       median_session_ms=median,median_cold_ms=cold_median,session_speed_ratio=median['v09']/median['v010'],
       binaries={n:dict(file=p.name,sha256=digest(p)) for n,p in exes.items()},
       host=dict(platform=platform.platform(),python=platform.python_version(),cpu_count=os.cpu_count()),
       caveats=['OS filesystem caches not flushed','one process per session, one thread',
                'source contents still read on every query','no neural training or generation',
                'no comparison with ripgrep or energy measurement','not a weak-PC measurement'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--root',type=Path,default=ROOT/'data/cpython_snapshot/documents');p.add_argument('--out',type=Path,default=ROOT/'results/v010/code_session.json');p.add_argument('--repeats',type=int,default=5);a=p.parse_args()
    if not 1<=a.repeats<=30:p.error('repeats 1..30')
    result=measure(a.build.resolve(),a.root.resolve(),a.repeats);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sources','cases','results','runs','cold_runs')},indent=2))
if __name__=='__main__':main()
