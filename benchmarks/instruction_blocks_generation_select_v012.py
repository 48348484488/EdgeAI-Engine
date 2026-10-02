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
