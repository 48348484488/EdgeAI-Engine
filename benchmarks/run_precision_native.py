#!/usr/bin/env python3
"""Native forward timing, not intelligence or a direct energy measurement."""
import argparse,json,platform,random,statistics,subprocess,tempfile
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--binary',type=Path,default=Path('build/edgeai_runtime_benchmark'))
    ap.add_argument('--tokens',type=int,default=50000)
    ap.add_argument('--rounds',type=int,default=7)
    ap.add_argument('--out',type=Path,default=Path('results/precision_native.json'))
    args=ap.parse_args()
    if not 1<=args.tokens<=1000000 or args.rounds<1:ap.error('invalid tokens/rounds')
    policies=['fp32','ternary','qk_fp32','memory_fp32','memory_int8','int8']
    cases=[(p,Path(f'models/recall/{p}-seed11.edge')) for p in policies]
    for p in ('memory_int8','int8','fp32'):
        file=Path(f'models/head_ptq/{p}-head-int8-seed11.edge')
        if file.exists():cases.append((p+'_head_int8',file))
    results=[];rng=random.Random(9274)
    with tempfile.TemporaryDirectory() as td:
        rss_path=Path(td)/'rss.txt'
        for repeat in range(args.rounds):
            order=list(cases);rng.shuffle(order)
            for name,path in order:
                cmd=[str(args.binary.resolve()),str(path),str(args.tokens),'auto']
                with_time=Path('/usr/bin/time').exists()
                if with_time:cmd=['/usr/bin/time','-f','%M','-o',str(rss_path)]+cmd
                run=subprocess.run(cmd,capture_output=True,text=True,check=True)
                row=json.loads(run.stdout);row.update(policy=name,round=repeat,model=str(path),
                    model_file_bytes=path.stat().st_size,peak_rss_kib=int(rss_path.read_text().strip()) if with_time else None)
                results.append(row)
    summary={}
    for name,_ in cases:
        group=[r for r in results if r['policy']==name]
        summary[name]=dict(median_seconds=statistics.median(r['seconds'] for r in group),
            median_cpu_seconds=statistics.median(r['cpu_seconds'] for r in group),
            min_seconds=min(r['seconds'] for r in group),max_seconds=max(r['seconds'] for r in group),
            median_us_per_byte_step=statistics.median(r['seconds']*1e6/r['tokens'] for r in group),
            weights_bytes=group[0]['weights_bytes'],file_bytes=group[0]['model_file_bytes'],
            median_peak_rss_kib=statistics.median(r['peak_rss_kib'] for r in group) if group[0]['peak_rss_kib'] is not None else None,
            state_payload_bytes=group[0]['state_payload_bytes'],numeric_working_bytes=group[0]['numeric_working_bytes'])
    cpu=None
    info=Path('/proc/cpuinfo')
    if info.exists():cpu=next((s.split(':',1)[1].strip() for s in info.read_text().splitlines() if s.startswith('model name')),None)
    report=dict(platform=platform.platform(),cpu_model=cpu,threads=1,tokens=args.tokens,rounds=args.rounds,
                model_seed=11,seed_selection='fixed first registered seed, not fastest/best checkpoint',
                clock='steady_clock for wall; std::clock for process CPU',energy_joules=None,
                warnings='Tiny synthetic-trained byte model. Not representative of old PCs. RSS includes allocator/runtime. INT8 still uses FP32 activations/accumulation. Not a general quality or energy benchmark.',
                summary=summary,runs=results)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
