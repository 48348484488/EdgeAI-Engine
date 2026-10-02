#!/usr/bin/env python3
"""Generation-aligned checkpoint selection helpers for EdgeAI v0.12.

Selection uses validation generation only. Held-out test rows are evaluated
only after a checkpoint has been selected.
"""
import math
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import score

CONTROL_KEYS=('protocol','seed','target_steps','threads','dataset_sha256','tokenizer_fingerprint',
              'dim','hidden','window','precision','batch','lr','weight_decay','clip_norm',
              'max_length','selection')


def build_identity(seed,blocks,target_steps,threads,dataset_sha256,tokenizer_fingerprint,config):
    if blocks not in (1,2) or int(target_steps)<4 or int(threads)!=1:
        raise ValueError('invalid generation-selection identity')
    required=('dim','hidden','window','precision')
    if any(k not in config for k in required):
        raise ValueError('incomplete Transformer config')
    return dict(
        protocol='edge-sft-v012-generation-selection-1',
        seed=int(seed),target_steps=int(target_steps),threads=int(threads),
        dataset_sha256=str(dataset_sha256),tokenizer_fingerprint=str(tokenizer_fingerprint),
        dim=int(config['dim']),hidden=int(config['hidden']),window=int(config['window']),
        precision=str(config['precision']),vocab_size=int(config.get('vocab_size',256)),
        batch=16,lr=.001,weight_decay=.01,clip_norm=1.0,max_length=128,
        selection='greedy validation correct; exact, NLL, then earlier-step tiebreaks',
        blocks=int(blocks))


def assert_fair_pair(one,two):
    if one.get('blocks')!=1 or two.get('blocks')!=2:
        raise ValueError('need blocks 1 and 2')
    missing=[k for k in CONTROL_KEYS if k not in one or k not in two]
    if missing:
        raise ValueError('missing generation-selection controls: '+','.join(missing))
    changed=[k for k in CONTROL_KEYS if one[k]!=two[k]]
    if changed:
        raise ValueError('unfair generation-selection pair: '+','.join(changed))
    return True


def selection_key(row):
    required=('step','greedy_correct','greedy_exact','validation_nll')
    if any(k not in row for k in required):
        raise ValueError('incomplete generation-selection row')
    step=int(row['step'])
    correct=int(row['greedy_correct'])
    exact=int(row['greedy_exact'])
    nll=float(row['validation_nll'])
    if step<1 or correct<0 or exact<0 or exact>correct or not math.isfinite(nll):
        raise ValueError('invalid generation-selection metrics')
    return (correct,exact,-nll,-step)


def select_checkpoint(rows):
    if not rows:
        raise ValueError('no validation checkpoints')
    return max(rows,key=selection_key)


def generation_metrics_from_outputs(rows,outputs):
    correct=exact=eos=0
    for row in rows:
        prompt=row['prompt']
        if prompt not in outputs:
            raise ValueError('missing validation generation')
        raw,stopped=outputs[prompt]
        if not isinstance(raw,bytes) or type(stopped) is not bool:
            raise ValueError('invalid validation generation')
        target=row['answer'].encode('utf-8')
        exact+=int(raw==target)
        correct+=int(score(row,raw))
        eos+=int(stopped)
    return dict(count=len(rows),correct=correct,exact=exact,eos=eos)


def validation_generation(model,tok,rows,greedy_fn=None):
    if greedy_fn is None:
        from sft_model import greedy as greedy_fn
    outputs={}
    for row in rows:
        prompt=row['prompt']
        if prompt in outputs:
            raise ValueError('validation prompts must be unique for deterministic selection')
        raw,_,stopped=greedy_fn(model,tok,prompt,max_tokens=32)
        if isinstance(raw,str):
            raw=raw.encode('utf-8')
        elif not isinstance(raw,bytes):
            raise ValueError('greedy output must be bytes or text')
        outputs[prompt]=(raw,bool(stopped))
    return generation_metrics_from_outputs(rows,outputs)
