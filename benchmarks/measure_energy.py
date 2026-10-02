#!/usr/bin/env python3
"""Optional Linux package RAPL readings. No watt/TDP guesses or fake measurements.
Package energy includes other processes; short runs and virtual machines limit it.
"""
import argparse, json, subprocess, time
from pathlib import Path

def sensors():
    found=[]
    root=Path('/sys/class/powercap')
    if not root.exists():return found
    for path in root.glob('**/energy_uj'):
        try:
            name=(path.parent/'name').read_text().strip()
            if not name.startswith('package'):continue  # avoid counting child domains twice
            reading=int(path.read_text());maximum=int((path.parent/'max_energy_range_uj').read_text())
            found.append((path,name,reading,maximum))
        except (OSError,ValueError):continue
    return found

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,default=Path('results/energy.json'));ap.add_argument('command',nargs=argparse.REMAINDER);args=ap.parse_args()
    cmd=args.command
    if cmd and cmd[0]=='--':cmd=cmd[1:]
    if not cmd:ap.error('provide a command after --')
    before=sensors();start=time.perf_counter();run=subprocess.run(cmd,capture_output=True,text=True);elapsed=time.perf_counter()-start
    domains=[]
    for path,name,value,maximum in before:
        try:
            after=int(path.read_text());delta=after-value
            if delta<0:delta+=maximum
            domains.append(dict(name=name,joules=delta/1e6))
        except (OSError,ValueError):pass
    measured=bool(domains) and len(domains)==len(before)
    result=dict(available=measured,package_energy_joules=sum(d['joules'] for d in domains) if measured else None,elapsed_seconds=elapsed,exit_code=run.returncode,domains=domains,stdout=run.stdout,stderr=run.stderr,limitations='Package energy, not process-isolated or whole-wall energy. At most one wrap can be corrected. No extrapolation from latency.',reason=None if measured else 'No readable package RAPL counters in this environment')
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));raise SystemExit(run.returncode)
if __name__=='__main__':main()
