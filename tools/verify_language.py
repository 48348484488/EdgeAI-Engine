#!/usr/bin/env python3
"""Parity gate: every logit for mixed precision, ring wrap and UTF-8/raw bytes."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import numpy as np
import torch
from transformer_model import TinyTransformer,export_transformer

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,default=Path('build'));p.add_argument('--out',type=Path,default=Path('results/v05/parity_transformer.json'));a=p.parse_args()
    torch.set_num_threads(1);binary=(a.build/'edgeai_logits').resolve();rows=[]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        for dim,hidden,window in ((8,13,1),(16,25,7),(64,96,64)):
            for precision in ('fp32','int8','ternary'):
                torch.manual_seed(519);m=TinyTransformer(dim=dim,hidden=hidden,window=window,precision=precision).eval()
                raw=bytes(range(256))+"ação CPU\n".encode('utf-8');x=torch.tensor([list(raw)])
                with torch.inference_mode():expected=m(x).numpy().reshape(-1,256)
                path=root/'model.edge';export_transformer(m,path);(root/'input.bin').write_bytes(raw)
                for kernel in ('auto','scalar','lookup2'):
                    subprocess.run([str(binary),str(path),str(root/'input.bin'),str(root/'out.f32'),kernel],check=True,capture_output=True)
                    actual=np.fromfile(root/'out.f32',dtype='<f4').reshape(-1,256)
                    err=float(np.max(np.abs(actual-expected)))
                    if not np.allclose(actual,expected,atol=4e-5,rtol=4e-5):raise AssertionError((dim,precision,kernel,err))
                    rows.append(dict(dim=dim,hidden=hidden,window=window,precision=precision,kernel=kernel,bytes=len(raw),max_abs_error=err,allclose=True))
    report=dict(cases=rows,count=len(rows),max_abs_error=max(r['max_abs_error'] for r in rows),atol=4e-5,rtol=4e-5)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
if __name__=='__main__':main()
