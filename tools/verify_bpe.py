#!/usr/bin/env python3
"""Cross-language byte-BPE IDs + all neural logits, including BOS and cache wrap."""
import argparse,json,subprocess,sys,tempfile
from pathlib import Path
import numpy as np
import torch
from byte_bpe import ByteBPE
from transformer_model import TinyTransformer,export_transformer

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,default=Path('build'));p.add_argument('--out',type=Path,default=Path('results/v06/parity.json'));a=p.parse_args()
    torch.set_num_threads(1);binary=a.build.resolve();rows=[]
    with tempfile.TemporaryDirectory() as td:
        d=Path(td);raw=bytes(range(256))+'ação, café, 🐈\n'.encode()+b'banana banana '+b'a'*113
        (d/'input').write_bytes(raw)
        for tokenizer in (ByteBPE(),ByteBPE.train([b'banana banana banana alphabet '+b'a'*200],280)):
            ids=tokenizer.encode(raw,True)
            for dim,hidden,window in ((8,13,1),(16,25,7),(48,128,64)):
                for precision in ('fp32','int8'):
                    torch.manual_seed(601);model=TinyTransformer(dim,hidden,window,precision,vocab_size=tokenizer.vocab_size).eval()
                    export_transformer(model,d/'m.edge',tokenizer=tokenizer)
                    actual_ids=json.loads(subprocess.check_output([str(binary/'edgeai_tokenize'),str(d/'m.edge'),str(d/'input')],text=True))['ids']
                    if actual_ids!=ids:raise AssertionError('native BPE IDs differ')
                    with torch.inference_mode():expected=model(torch.tensor([ids])).numpy()[0]
                    for kernel in ('scalar','auto'):
                        subprocess.run([str(binary/'edgeai_logits'),str(d/'m.edge'),str(d/'input'),str(d/'z.f32'),kernel],check=True,capture_output=True)
                        actual=np.fromfile(d/'z.f32',dtype='<f4').reshape(-1,tokenizer.vocab_size)
                        error=float(np.max(np.abs(actual-expected)))
                        if not np.allclose(actual,expected,atol=4e-5,rtol=4e-5):raise AssertionError((dim,precision,kernel,error))
                        rows.append(dict(vocab=tokenizer.vocab_size,dim=dim,window=window,precision=precision,kernel=kernel,tokens=len(ids),max_abs_error=error))
    report=dict(cases=rows,count=len(rows),atol=4e-5,rtol=4e-5,max_abs_error=max(r['max_abs_error'] for r in rows),all_passed=True)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
if __name__=='__main__':main()
