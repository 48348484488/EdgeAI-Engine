#!/usr/bin/env python3
"""Audit ARM64 main-function call dependencies against generated C++ sources.

This is a source-blind structural audit. Presence of generated C++ does not
prove compilation, execution, ABI correctness, or behavioral equivalence.
"""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

SOURCE_NAME = re.compile(r'^candidate_([0-9a-fA-F]+)\.cpp$')
HEX = re.compile(r'^0x[0-9a-fA-F]+$')


def generated_functions(folder):
    """Require source filenames and exported function names to agree."""
    if not folder.is_dir():
        raise ValueError('generated C++ directory does not exist')
    found = {}
    for source in sorted(folder.glob('candidate_*.cpp')):
        match = SOURCE_NAME.fullmatch(source.name)
        if not match:
            raise ValueError(f'invalid generated filename: {source.name}')
        addr = int(match.group(1), 16)
        if addr in found:
            raise ValueError(f'duplicate generated function address: {addr:#x}')
        source_bytes = source.read_bytes()
        source_text = source_bytes.decode('utf-8')
        if not re.search(r'extern\s+"C"\s+[^{;]+\brecovered_' + format(addr, 'x') + r'\s*\(', source_text):
            raise ValueError(f'missing matching exported C++ function: {source.name}')
        found[addr] = {'file': source.name, 'sha256': hashlib.sha256(source_bytes).hexdigest()}
    if not found:
        raise ValueError('no generated C++ candidate functions')
    return found


def audit(cfg, generated, expected_binary_sha256=None):
    if cfg.get('source_read') is not False or cfg.get('behaviorally_validated') is not False:
        raise ValueError('CFG must explicitly declare source-blind and unvalidated status')
    binary_sha = cfg.get('binary_sha256', '')
    if not isinstance(binary_sha, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', binary_sha):
        raise ValueError('CFG is missing binary SHA-256')
    if expected_binary_sha256 and binary_sha.lower() != expected_binary_sha256.lower():
        raise ValueError('binary SHA-256 does not match expected ELF')
    calls = cfg.get('calls')
    if not isinstance(calls, list):
        raise ValueError('CFG has no call list')
    classified = []
    counts = Counter()
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call.get('pc'), str) or not HEX.fullmatch(call['pc']):
            raise ValueError('malformed call site')
        symbol = call.get('symbol')
        target = call.get('target')
        if call.get('indirect'):
            category = 'indirect_unresolved'
            if target is not None:
                raise ValueError('indirect call must not claim a static target')
        elif target is None or not isinstance(target, str) or not HEX.fullmatch(target):
            raise ValueError(f'direct call missing target at {call["pc"]}')
        elif isinstance(symbol, str) and symbol.endswith('@plt'):
            category = 'external_plt'
        elif int(target, 16) in generated:
            category = 'generated_cpp'
        else:
            category = 'missing_internal_cpp'
        counts[category] += 1
        classified.append({'pc': call['pc'], 'target': target, 'symbol': symbol,
                           'category': category})
    distinct_missing = sorted({int(c['target'], 16) for c in classified
                               if c['category'] == 'missing_internal_cpp'})
    return {
        'binary_sha256': binary_sha.lower(),
        'main_start': cfg.get('start'),
        'main_end_exclusive': cfg.get('end_exclusive'),
        'call_sites': len(classified),
        'distinct_targets': len({c['target'] for c in classified if c['target'] is not None}),
        'generated_cpp_sources': len(generated),
        'calls_to_generated_cpp': counts['generated_cpp'],
        'calls_to_external_plt': counts['external_plt'],
        'calls_missing_internal_cpp': counts['missing_internal_cpp'],
        'indirect_unresolved_calls': counts['indirect_unresolved'],
        'missing_internal_targets': [hex(a) for a in distinct_missing],
        'calls': classified,
        'complete': False,
        'limitations': 'Source-blind structural dependency audit only; generated files are not proof of valid ABI, behavioral equivalence, or an executable game.'
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cfg', required=True, type=Path)
    p.add_argument('--generated-dir', required=True, type=Path)
    p.add_argument('--expected-sha256')
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    result = audit(json.loads(args.cfg.read_text()), generated_functions(args.generated_dir), args.expected_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['call_sites']} call sites; {result['calls_to_generated_cpp']} generated C++; "
          f"{result['calls_to_external_plt']} external PLT; "
          f"{result['calls_missing_internal_cpp']} missing internal calls "
          f"({', '.join(result['missing_internal_targets'])}); not executable")


if __name__ == '__main__':
    main()
