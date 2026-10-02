#!/usr/bin/env python3
"""Diagnostic only: local lexical retrieval, NOT neural model accuracy."""
import argparse
import hashlib
import json
import platform
import statistics
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from workbench import search_code,write_json

def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--out',type=Path,default=ROOT/'results/v09/retrieval.json');args=p.parse_args()
 manifest=json.loads((ROOT/'docs/v09/fixture_hashes.json').read_text())
 for path,digest in manifest.items():
  if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=digest:raise ValueError('fixture hash mismatch: '+path)
 fixture=ROOT/'data/code_demo';cases=json.loads((fixture/'cases.json').read_text())
 rows=[]
 for case in cases:
  runs=[search_code(fixture,case['query'],build=args.build,limit=3) for _ in range(3)]
  result=runs[0];hits=result['hits']
  for hit in hits:
   lines=(fixture/hit['path']).read_text(encoding='utf-8').splitlines()
   if '\n'.join(lines[hit['start_line']-1:hit['end_line']])!=hit['text']:raise ValueError('snippet/source mismatch')
  expected=case['path']
  hit1=bool(hits and hits[0]['path']==expected and hits[0]['match_line']==case['line']) if expected else not hits
  hit3=any(h['path']==expected and h['match_line']==case['line'] for h in hits) if expected else not hits
  rows.append(dict(case=case,top1_correct=hit1,top3_correct=hit3,runs=runs))
 positives=[r for r in rows if r['case']['path']];negatives=[r for r in rows if not r['case']['path']]
 probe=search_code(ROOT,'Onde fica a função greedy_token?',build=args.build,limit=3)
 obj={'schema':1,'method':'deterministic lexical retrieval; no model','host':platform.platform(),
      'cases':len(rows),'positive_cases':len(positives),'negative_cases':len(negatives),
      'positive_top1':sum(r['top1_correct'] for r in positives),'positive_top3':sum(r['top3_correct'] for r in positives),
      'negative_empty':sum(r['top1_correct'] for r in negatives),
      'median_seconds_including_process':statistics.median(x['wall_seconds_including_process'] for r in rows for x in r['runs']),
      'all_snippets_match_source':True,'rows':rows,'self_project_probe':probe,
      'energy_joules':None,'limitations':['small authored fixture, not independent benchmark','same symbols in question and source; lexical retrieval only','source is rescanned per process','absence in inspected scope is not absence in entire project']}
 write_json(args.out,obj)
 print(json.dumps({k:v for k,v in obj.items() if k not in ('rows','self_project_probe')},indent=2))
if __name__=='__main__':main()
