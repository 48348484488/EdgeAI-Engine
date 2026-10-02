#!/usr/bin/env python3
"""Verify Python/native logit parity for one- and two-block Transformers."""
import argparse
import json
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import torch

from transformer_model import TinyTransformer, export_transformer

ROOT=Path(__file__).resolve().parents[1]


def verify(build, out):
    build=Path(build).resolve();out=Path(out)
    binary=build/'edgeai_token_logits'
    if not binary.is_file():
        raise FileNotFoundError('missing native token logit tool: '+str(binary))
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    ids=[3,17,5,201,8,9,10,11,12,13,14]
    rows=[]
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        token_path=td/'ids.u32'
        token_path.write_bytes(struct.pack('<'+'I'*len(ids),*ids))
        for blocks in (1,2):
            torch.manual_seed(1200+blocks)
            model=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',blocks=blocks)
            model.eval()
            model_path=td/f'b{blocks}.edge'
            export_transformer(model,model_path,max_generate=16)
            with torch.inference_mode():
                expected=model(torch.tensor([ids],dtype=torch.long)).cpu().numpy()[0].astype(np.float32,copy=False)
            for kernel in ('scalar','auto'):
                native_path=td/f'b{blocks}-{kernel}.f32'
                proc=subprocess.run(
                    [str(binary),str(model_path),str(token_path),str(native_path),kernel],
                    capture_output=True,text=True,timeout=30)
                if proc.returncode:
                    raise RuntimeError(f'native parity command failed ({blocks}, {kernel}): {proc.stderr}')
                actual=np.fromfile(native_path,dtype='<f4')
                if actual.size!=expected.size:
                    raise AssertionError((blocks,kernel,'logit count',actual.size,expected.size))
                actual=actual.reshape(expected.shape)
                error=float(np.max(np.abs(actual-expected)))
                passed=bool(np.allclose(actual,expected,atol=6e-5,rtol=6e-5))
                if not passed:
                    raise AssertionError((blocks,kernel,'parity',error))
                rows.append(dict(blocks=blocks,kernel=kernel,tokens=len(ids),window=model.window,
                                 max_abs_error=error,passed=True,
                                 format='EDGEAI8' if blocks>1 else 'EDGEAI5'))
    report=dict(all_passed=True,cases=rows,max_abs_error=max(r['max_abs_error'] for r in rows),
                atol=6e-5,rtol=6e-5,note='sequence length exceeds attention window to exercise KV cache wrap')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,default=ROOT/'build')
    p.add_argument('--out',type=Path,default=ROOT/'results/v012/multiblock_parity.json')
    a=p.parse_args()
    report=verify(a.build,a.out)
    print(json.dumps(dict(all_passed=report['all_passed'],cases=len(report['cases']),
                          max_abs_error=report['max_abs_error'])))


if __name__=='__main__':
    main()
