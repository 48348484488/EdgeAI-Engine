#!/usr/bin/env python3
"""Controlled v0.12 one-block vs two-block instruction experiment.

The experiment keeps all declared controls identical and permits only the
Transformer block count to differ inside a paired comparison.
"""
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
