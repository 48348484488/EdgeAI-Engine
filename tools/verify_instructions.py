#!/usr/bin/env python3
"""Verify every logit and greedy termination in native C++ against Python."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import numpy as np
import torch
from instruction_data import load_dataset,sha
from sft_model import tokenizer_from_payload,greedy
from transformer_model import TinyTransformer
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--report',type=Path,default=ROOT/'results/v07/training.json');p.add_argument('--out',type=Path,default=ROOT/'results/v07/parity.json');a=p.parse_args()
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);report=json.loads(a.report.read_text());rows=[];generation=[]
    data,_=load_dataset(ROOT/'data/instructions_v07')
    if report.get('completed')!=report['expected']:raise ValueError('incomplete training')
    examples=[next(r for r in data['test_id'] if r['task']==task) for task in ('copy','uppercase','addition','expression')]
    build=a.build.resolve()
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for trial in report['runs']:
            for phase in ('before','after'):
                path=ROOT/trial[phase+'_path'];pt=path.with_suffix('.pt')
                for f in (path,pt):
                    if sha(f.read_bytes())!=trial['artifacts'][str(f.relative_to(ROOT))]:raise ValueError('artifact mismatch')
                cp=torch.load(pt,map_location='cpu',weights_only=True);tok=tokenizer_from_payload(cp['tokenizer']);model=TinyTransformer(**cp['config']);model.load_state_dict(cp['state_dict']);model.eval()
                fixtures=[tok.encode_prompt(b'')+[tok.eos_id],tok.encode_prompt(bytes(range(256)))+tok.encode('ação 😀')+[tok.eos_id],
                          tok.encode_prompt(examples[0]['prompt'])+tok.encode(examples[0]['answer'])+[tok.eos_id]]
                for fi,ids in enumerate(fixtures):
                    (td/'ids.u32').write_bytes(struct.pack('<'+'I'*len(ids),*ids))
                    with torch.inference_mode():expected=model(torch.tensor([ids])).numpy()[0]
                    for kernel in ('scalar','auto'):
                        subprocess.run([str(build/'edgeai_token_logits'),str(path),str(td/'ids.u32'),str(td/'logits.f32'),kernel],capture_output=True,check=True)
                        actual=np.fromfile(td/'logits.f32',dtype='<f4').reshape(-1,tok.vocab_size)
                        error=float(np.max(np.abs(actual-expected)))
                        if not np.allclose(actual,expected,atol=6e-5,rtol=6e-5):raise AssertionError((trial['seed'],phase,fi,kernel,error))
                        rows.append(dict(seed=trial['seed'],phase=phase,fixture=fi,kernel=kernel,tokens=len(ids),max_abs_error=error))
                for ex in examples:
                    raw,ids,stopped=greedy(model,tok,ex['prompt'],32);(td/'prompt').write_bytes(ex['prompt'].encode())
                    meta=json.loads(subprocess.check_output([str(build/'edgeai_generate'),str(path),str(td/'prompt'),str(td/'output'),'32'],text=True))
                    if (td/'output').read_bytes()!=raw or meta['generated_tokens']!=len(ids) or meta['stopped_on_eos']!=stopped:raise AssertionError('native greedy/EOS mismatch')
                    generation.append(dict(seed=trial['seed'],phase=phase,example_id=ex['id'],generated_tokens=len(ids),stopped_on_eos=stopped,matched=True))
    output=dict(all_passed=True,logit_cases=rows,greedy_cases=generation,max_abs_error=max(r['max_abs_error'] for r in rows),atol=6e-5,rtol=6e-5,
                training_report_sha256=sha(a.report.read_bytes()))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(dict(all_passed=True,logit_cases=len(rows),greedy_cases=len(generation),max_abs_error=output['max_abs_error'])))
if __name__=='__main__':main()
