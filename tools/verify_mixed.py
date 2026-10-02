#!/usr/bin/env python3
"""Check every logit from EDGEAI4 under all policies and kernels, plus malformed files."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
import torch
from mixed_model import MixedHybrid, POLICIES, export_mixed, numeric_weight_bytes
from verify_parity import compare

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--inspect',type=Path,required=True)
    p.add_argument('--checkpoint-dir',type=Path,default=Path('models/recall'))
    p.add_argument('--demo',type=Path,default=Path('models/mixed_tiny.pt'))
    p.add_argument('--out',type=Path,default=Path('results/mixed_parity.json'))
    args=p.parse_args();torch.set_num_threads(1);cases=[];results=[]
    for policy in POLICIES:
        for shape in ((17,31,7,5,3),(32,64,16,16,1)):
            torch.manual_seed(918)
            model=MixedHybrid(*shape,policy=policy)
            cases.append((f'{policy}-{shape[0]}.edge',model,bytes(range(130))))
    for out in ('int8','ternary'):
        torch.manual_seed(333)
        cases.append((f'output-{out}.edge',MixedHybrid(17,31,7,5,2,policy='memory_int8',output_precision=out),bytes(range(256))))
    checkpoints=sorted(args.checkpoint_dir.glob('*.pt'))
    checkpoints+=sorted((args.checkpoint_dir.parent/'head_ptq').glob('*.pt'))
    if args.demo.exists():checkpoints.append(args.demo)
    for path in checkpoints:
        data=torch.load(path,map_location='cpu',weights_only=True)
        if data.get('kind')=='transformer_fp32':continue
        model=MixedHybrid(**data['config']);model.load_state_dict(data['state_dict'])
        cases.append((path.stem+'.edge',model,bytes(range(96))))
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for name,model,payload in cases:
            model.eval();filename=td/name;export_mixed(model,filename)
            info=subprocess.run([str(args.inspect.resolve()),str(filename)],capture_output=True,text=True,check=True)
            fields=dict(line.split('=',1) for line in info.stdout.splitlines() if '=' in line)
            if int(fields['resident_numeric_weights_bytes'])!=numeric_weight_bytes(model):
                raise AssertionError('native weight accounting differs: '+name)
            for kernel in ('scalar','lookup2','auto'):
                results.append(compare(args.binary.resolve(),model,filename,payload,kernel,td))
        # A model-level invalid tag, truncation or trailing data must fail without execution.
        filename=td/'malformed.edge';model=MixedHybrid(16,32,8,8,1);export_mixed(model,filename)
        good=filename.read_bytes();tag=56+256*16*4
        mutations=[good[:tag]+b'\xff\xff\xff\xff'+good[tag+4:],good[:-1],good+b'EXTRA',good[:20]]
        for damaged in mutations:
            filename.write_bytes(damaged)
            run=subprocess.run([str(args.inspect.resolve()),str(filename)],capture_output=True)
            if run.returncode==0:raise AssertionError('malformed EDGEAI4 was accepted')
    report=dict(logit_cases=results,malformed_models_rejected=len(mutations),
                total_cases=len(results),maximum_absolute_error=max(r['max_absolute_error'] for r in results),
                relative_tolerance=3e-5,absolute_tolerance=3e-5,
                note='All logits compared, not merely generated text. Weight byte accounting checked per model.')
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
