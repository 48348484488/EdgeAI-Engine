#!/usr/bin/env python3
"""Interleaved native timings; reports byte steps, not useful answers/tokens-BPE."""
import argparse
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from language_data import sha256

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--report',type=Path,default=ROOT/'results/v05/language.json');p.add_argument('--out',type=Path,default=ROOT/'results/v05/native.json');p.add_argument('--repeats',type=int,default=5);p.add_argument('--tokens',type=int,default=10000);a=p.parse_args()
    if a.repeats<1 or not 1<=a.tokens<=1000000:p.error('invalid repetitions/tokens')
    report=json.loads(a.report.read_text());binary=(a.build/'edgeai_runtime_benchmark').resolve()
    cpu=sorted(os.sched_getaffinity(0))[0] if hasattr(os,'sched_getaffinity') else None
    schedule=[(r,j) for r in report['runs'] for j in range(a.repeats)];random.Random(381).shuffle(schedule);rows=[]
    with tempfile.TemporaryDirectory() as td:
        for run,j in schedule:
            model=ROOT/run['model_path'];cmd=[str(binary),str(model),str(a.tokens),'auto']
            if sha256(model.read_bytes())!=run['artifacts'][run['model_path']]:raise ValueError('model changed since quality measurement')
            if cpu is not None and Path('/usr/bin/taskset').is_file():cmd=['/usr/bin/taskset','-c',str(cpu)]+cmd
            rssfile=Path(td)/'rss';has_time=Path('/usr/bin/time').is_file()
            if has_time:cmd=['/usr/bin/time','-f','%M','-o',str(rssfile)]+cmd
            proc=subprocess.run(cmd,capture_output=True,text=True,check=True);row=json.loads(proc.stdout)
            row.update(kind=run['kind'],seed=run['seed'],repeat=j,peak_rss_kib=int(rssfile.read_text().strip()) if has_time else None,model_sha256=sha256(model.read_bytes()))
            rows.append(row)
    summary={}
    for kind in sorted({r['kind'] for r in rows}):
        group=[r for r in rows if r['kind']==kind];rss=[r['peak_rss_kib'] for r in group if r['peak_rss_kib'] is not None]
        summary[kind]=dict(median_us_per_byte=statistics.median(r['seconds']*1e6/r['tokens'] for r in group),median_cpu_us_per_byte=statistics.median(r['cpu_seconds']*1e6/r['tokens'] for r in group),min_us_per_byte=min(r['seconds']*1e6/r['tokens'] for r in group),max_us_per_byte=max(r['seconds']*1e6/r['tokens'] for r in group),median_rss_kib=statistics.median(rss) if rss else None,weights_bytes=group[0]['weights_bytes'],state_payload_bytes=group[0]['state_payload_bytes'],numeric_working_bytes=group[0]['numeric_working_bytes'])
    cpu_name='unknown'
    if Path('/proc/cpuinfo').is_file():
        cpu_name=next((s.split(':',1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines() if s.startswith('model name')),'unknown')
    out=dict(platform=platform.platform(),cpu=cpu_name,affinity_cpu=cpu,one_inference_thread=True,repeats=a.repeats,tokens=a.tokens,binary_sha256=sha256(binary.read_bytes()),summary=summary,runs=rows,energy_joules=None,limitations='VM host, not weak PC. RSS whole process, timers exclude model load and warmup. All numbers measure teacher-forced byte steps, not BPE tokens or useful answers. No energy inference.')
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
