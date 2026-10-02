#!/usr/bin/env python3
"""Revalidate shipped trained checkpoints against the final native executable."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
import numpy as np
import torch
from mixed_model import MixedHybrid
from transformer_model import TinyTransformer
from language_data import sha256
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--report',type=Path,default=ROOT/'results/v05/language.json');p.add_argument('--out',type=Path,default=ROOT/'results/v05/trained_parity.json');a=p.parse_args()
    torch.set_num_threads(1);report=json.loads(a.report.read_text());rows=[]
    rng=np.random.default_rng(9141);raw=bytes(rng.integers(0,256,289,dtype=np.uint8))
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);(td/'input.bin').write_bytes(raw)
        for run in report['runs']:
            edge=ROOT/run['model_path'];checkpoint=torch.load(edge.with_suffix('.pt'),map_location='cpu',weights_only=True)
            model=(TinyTransformer if run['kind'].startswith('transformer_') else MixedHybrid)(**checkpoint['config']);model.load_state_dict(checkpoint['state_dict']);model.eval()
            with torch.inference_mode():expected=model(torch.tensor([list(raw)])).numpy().reshape(-1,256)
            subprocess.run([str((a.build/'edgeai_logits').resolve()),str(edge),str(td/'input.bin'),str(td/'out.f32'),'auto'],capture_output=True,check=True)
            actual=np.fromfile(td/'out.f32',dtype='<f4').reshape(-1,256);error=float(np.max(np.abs(expected-actual)))
            if not np.allclose(actual,expected,atol=6e-5,rtol=6e-5):raise AssertionError((run['kind'],run['seed'],error))
            metrics={}
            for domain in ('code','text'):
                output=subprocess.check_output([str((a.build/'edgeai_evaluate').resolve()),str(edge),str(ROOT/f'data/project_corpus/test_{domain}.blocks')],text=True);native=json.loads(output);reference=run['metrics'][domain]
                if native['targets']!=reference['targets'] or native['correct']!=reference['correct'] or abs(native['bits_per_byte']-reference['bits_per_byte'])>3e-5:raise AssertionError('final evaluator metrics changed')
                metrics[domain]=native
            rows.append(dict(kind=run['kind'],seed=run['seed'],trace_bytes=len(raw),max_abs_error=error,logits_allclose=True,predictions_agree=bool((actual.argmax(-1)==expected.argmax(-1)).all()),native_metrics=metrics))
    result=dict(cases=rows,max_abs_error=max(r['max_abs_error'] for r in rows),trace_sha256=sha256(raw),atol=6e-5,rtol=6e-5,final_logits_binary_sha256=sha256((a.build/'edgeai_logits').read_bytes()),final_evaluate_binary_sha256=sha256((a.build/'edgeai_evaluate').read_bytes()))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print('Trained parity cases:',len(rows),'max_abs_error:',result['max_abs_error'])
if __name__=='__main__':main()
