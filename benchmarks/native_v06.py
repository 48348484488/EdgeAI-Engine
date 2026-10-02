#!/usr/bin/env python3
"""All-logit checks + same-raw-text native timing, separate load and tokenizer."""
import argparse,json,os,random,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import numpy as np
import torch
from byte_bpe import ByteBPE
from external_data import load_snapshot,sha
from transformer_model import TinyTransformer

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--report',type=Path,default=ROOT/'results/v06/training.json');p.add_argument('--out',type=Path,default=ROOT/'results/v06/native.json');p.add_argument('--repeats',type=int,default=5);a=p.parse_args()
    if not 1<=a.repeats<=20:p.error('repeats in 1..20')
    torch.set_num_threads(1);load_snapshot(ROOT/'data/cpython_snapshot');training=json.loads(a.report.read_text());build=a.build.resolve();rows=[];parities=[];generations=[]
    if len(training['runs'])!=training['expected']:raise RuntimeError('training report incomplete')
    cpu=min(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None
    pin=['taskset','-c',str(cpu)] if cpu is not None else []
    with tempfile.TemporaryDirectory() as td:
        d=Path(td);raw=bytes(range(256))+b'\nclass Task:\n    def compute(self, x):\n        return x + 2\n'+('ação: CPU sem GPU\n'.encode())
        (d/'input').write_bytes(raw)
        for row in training['runs']:
            for f,h in row['artifacts'].items():
                if sha((ROOT/f).read_bytes())!=h:raise AssertionError('artifact changed')
            modelpath=ROOT/row['model_path'];ck=torch.load(modelpath.with_suffix('.pt'),map_location='cpu',weights_only=True)
            model=TinyTransformer(**ck['config']);model.load_state_dict(ck['state_dict']);model.eval();tok=ByteBPE(ck['tokenizer']['merges']);ids=tok.encode(raw,True)
            actual_ids=json.loads(subprocess.check_output([str(build/'edgeai_tokenize'),str(modelpath),str(d/'input')],text=True))['ids']
            if ids!=actual_ids:raise AssertionError('trained native tokenizer mismatch')
            with torch.inference_mode():expected=model(torch.tensor([ids])).numpy()[0]
            subprocess.run([str(build/'edgeai_logits'),str(modelpath),str(d/'input'),str(d/'logits')],check=True,capture_output=True)
            actual=np.fromfile(d/'logits',dtype='<f4').reshape(-1,tok.vocab_size);error=float(np.max(np.abs(expected-actual)))
            if not np.allclose(expected,actual,atol=6e-5,rtol=6e-5):raise AssertionError(('trained logits',row['kind'],error))
            parities.append(dict(kind=row['kind'],seed=row['seed'],tokens=len(ids),max_abs_error=error,passed=True))
            (d/'prompt').write_bytes(b'def add_values(a, b):\n    return ')
            g=json.loads(subprocess.check_output(pin+[str(build/'edgeai_generate'),str(modelpath),str(d/'prompt'),str(d/'output'),'64'],text=True));g.update(kind=row['kind'],seed=row['seed'],output_hex=(d/'output').read_bytes().hex());generations.append(g)
        jobs=[(r,k) for k in range(a.repeats) for r in training['runs']];random.Random(606).shuffle(jobs)
        for row,rep in jobs:
            cmd=pin+[str(build/'edgeai_text_eval'),str(ROOT/row['model_path']),str(ROOT/'data/cpython_snapshot/test.rawblocks')]
            rss_path=d/'rss'
            if Path('/usr/bin/time').exists():cmd=['/usr/bin/time','-f','%M','-o',str(rss_path)]+cmd
            native=json.loads(subprocess.check_output(cmd,text=True));native.update(kind=row['kind'],seed=row['seed'],repetition=rep,rss_peak_kib=int(rss_path.read_text().strip()) if rss_path.exists() else None)
            if native['raw_bytes']!=row['metrics']['raw_bytes'] or abs(native['bits_per_byte']-row['metrics']['bits_per_byte'])>4e-5:raise AssertionError('native same-text score changed')
            rows.append(native)
    report=dict(parity=parities,repeats=a.repeats,cpu_affinity=cpu,rows=rows,generation=generations,note='all rows score the same 29480 raw test bytes; tokenization and model load separately measured; output tokens/sec is not compared as equal work; host is not a weak PC')
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'parity_models':len(parities),'repetitions':len(rows),'max_error':max(r['max_abs_error'] for r in parities)}))
if __name__=='__main__':main()
