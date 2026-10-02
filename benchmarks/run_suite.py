#!/usr/bin/env python3
"""Measure native CPU kernels with shared inputs and isolated numeric validation."""
import argparse, datetime, json, os, platform, subprocess, tempfile
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',type=Path,default=Path('build'));ap.add_argument('--out',type=Path,default=Path('results/native.json'));args=ap.parse_args()
    exe='.exe' if os.name=='nt' else ''
    directory=args.build.resolve()
    if not (directory/('edgeai_matrix_benchmark'+exe)).exists() and (directory/'Release').exists():directory=directory/'Release'
    def run(name,*extra):
        text=subprocess.check_output([str(directory/(name+exe)),*map(str,extra)],text=True)
        return json.loads(text)
    cases=[run('edgeai_matrix_benchmark',n,reps,7) for n,reps in [(64,1024),(256,128),(1024,16),(2048,8)]]
    runtime=run('edgeai_runtime_benchmark','models/hybrid_tiny.edge',20000)
    memory=None
    if Path('/usr/bin/time').exists():
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'rss.txt'
            subprocess.run(['/usr/bin/time','-f','%M','-o',str(target),str(directory/'edgeai_runtime_benchmark'),'models/hybrid_tiny.edge','20000'],check=True,capture_output=True)
            memory=int(target.read_text().strip())
    cpuinfo=Path('/proc/cpuinfo').read_text() if Path('/proc/cpuinfo').exists() else ''
    model_name=next((line.split(':',1)[1].strip() for line in cpuinfo.splitlines() if line.startswith('model name')),platform.processor())
    report=dict(utc_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),platform=platform.platform(),cpu=model_name,logical_cpus=os.cpu_count(),cpu_quota=Path('/sys/fs/cgroup/cpu.max').read_text().strip() if Path('/sys/fs/cgroup/cpu.max').exists() else None,threads_per_case=1,compiler=subprocess.check_output(['c++','--version'],text=True).splitlines()[0],kernel_cases=cases,runtime=runtime,runtime_process_peak_rss_kib=memory,limitations=['Virtualized shared host, not the user PC','Tiny model; byte steps are not subword tokens or useful responses','Dense comparison is our C++ implementation, not optimized BLAS or llama.cpp','Weights exclude workspace and process overhead; workspace is reported separately','No energy inference from timing'])
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
