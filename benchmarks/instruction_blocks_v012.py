#!/usr/bin/env python3
"""Controlled v0.12 one-block vs two-block instruction experiment.

The experiment keeps all declared controls identical and permits only the
Transformer block count to differ inside a paired comparison.
"""
import copy
import sys
from pathlib import Path

import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from transformer_model import TinyTransformer
SEEDS=(11,22,33)
ARCHITECTURES=(1,2)
DEFAULT_THREADS=1
DEFAULT_CPU_SECONDS=60.0

_CONTROL_KEYS=(
    'protocol','seed','cpu_budget','threads','dataset_sha256',
    'tokenizer_fingerprint','dim','hidden','window','precision',
    'batch','lr','weight_decay','clip_norm','max_length','selection',
)


def assert_fair_pair(one,two):
    """Reject a 1x2 comparison if anything controlled differs."""
    if one.get('blocks')!=1 or two.get('blocks')!=2:
        raise ValueError('paired architectures must be blocks=1 and blocks=2')
    missing=[key for key in _CONTROL_KEYS if key not in one or key not in two]
    if missing:
        raise ValueError('missing controlled identity fields: '+','.join(missing))
    changed=[key for key in _CONTROL_KEYS if one[key]!=two[key]]
    if changed:
        raise ValueError('unfair paired comparison: '+','.join(changed))
    return True


def promote_blocks(base,blocks,seed):
    """Return an independent N-block model while preserving the trained base path."""
    if not isinstance(base,TinyTransformer) or len(base.blocks)!=1:
        raise ValueError('promotion requires a one-block TinyTransformer base')
    if not 1<=blocks<=8:
        raise ValueError('blocks must be in [1,8]')
    if blocks==1:
        return copy.deepcopy(base)
    config=base.export_config()
    config['blocks']=blocks
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(int(seed)+12000)
        promoted=TinyTransformer(**config)
    promoted.emb.load_state_dict(base.emb.state_dict())
    promoted.out.load_state_dict(base.out.state_dict())
    promoted.blocks[0].load_state_dict(base.blocks[0].state_dict())
    promoted.train(base.training)
    return promoted
