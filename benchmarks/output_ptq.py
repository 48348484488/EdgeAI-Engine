#!/usr/bin/env python3
"""Separate, frozen-checkpoint INT8 output-head quantization experiment.
No retraining, seed selection or modification of the primary comparison.
"""
import argparse,json,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import torch
from mixed_model import MixedHybrid,numeric_weight_bytes,export_mixed
from precision_v04 import batch,evaluate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--quality',type=Path,default=Path('results/precision_quality.json'))
    p.add_argument('--out',type=Path,default=Path('results/output_ptq.json'))
    p.add_argument('--models',type=Path,default=Path('models/head_ptq'))
    args=p.parse_args();torch.set_num_threads(1)
    quality=json.loads(args.quality.read_text());tests={}
    for length,seed in quality['test_seed_by_length'].items():
        generator=torch.Generator().manual_seed(seed)
        tests[length]=[batch(32,int(length),generator) for _ in range(quality['test_size']//32)]
    args.models.mkdir(parents=True,exist_ok=True);rows=[]
    for old in quality['runs']:
        if old['kind'] not in ('fp32','int8','memory_int8'):continue
        checkpoint=Path(old['checkpoint']);data=torch.load(checkpoint,map_location='cpu',weights_only=True)
        config=dict(data['config']);config['output_precision']='int8'
        model=MixedHybrid(**config);model.load_state_dict(data['state_dict']);model.eval()
        result={length:evaluate(model,batches) for length,batches in tests.items()}
        name=f"{old['kind']}-head-int8-seed{old['seed']}";out=args.models/name
        export_mixed(model,out.with_suffix('.edge'))
        torch.save(dict(config=config,state_dict=model.state_dict(),kind='output_ptq',source_checkpoint=str(checkpoint)),out.with_suffix('.pt'))
        rows.append(dict(policy=old['kind'],seed=old['seed'],baseline_metrics=old['metrics'],quantized_metrics=result,
                         baseline_weight_bytes=old['numeric_weight_bytes'],weight_bytes=numeric_weight_bytes(model),
                         edge_file_bytes=out.with_suffix('.edge').stat().st_size,source=str(checkpoint),model=str(out.with_suffix('.edge'))))
    summary={}
    for policy in ('fp32','memory_int8','int8'):
        group=[r for r in rows if r['policy']==policy]
        summary[policy]=dict(weight_bytes=group[0]['weight_bytes'],edge_file_bytes=group[0]['edge_file_bytes'],
            by_length={length:dict(baseline_mean_accuracy=statistics.mean(r['baseline_metrics'][length]['accuracy'] for r in group),
                                  quantized_mean_accuracy=statistics.mean(r['quantized_metrics'][length]['accuracy'] for r in group)) for length in tests})
    report=dict(experiment='INT8 output head applied after primary fixed training; no retraining',
                caveat='Same held-out examples re-used for a declared separate ablation; not new confirmation of language/general intelligence',
                summary=summary,runs=rows)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
