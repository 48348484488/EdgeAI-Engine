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


def decode_bl_sites(code, base, start, end):
    """Independently decode AArch64 direct BL targets from executable bytes."""
    import struct
    if start % 4 or end % 4 or start >= end or start < base or end > base + len(code):
        raise ValueError('invalid main range in ELF .text')
    result = []
    for pc in range(start, end, 4):
        word, = struct.unpack_from('<I', code, pc - base)
        if word & 0xfc000000 != 0x94000000:
            continue
        imm = word & 0x03ffffff
        if imm & 0x02000000:
            imm -= 0x04000000
        result.append((pc, pc + imm * 4))
    return result


def verify_cfg_against_elf(cfg, elf):
    """Reject stale, missing, fabricated or retargeted direct calls in a CFG."""
    from aarch64_stripped_discovery import load_text
    info = load_text(elf)
    if cfg.get('binary_sha256', '').lower() != info['sha256']:
        raise ValueError('CFG SHA-256 does not match actual ELF')
    try:
        start = int(cfg['start'], 16)
        end = int(cfg['end_exclusive'], 16)
        recorded = Counter((int(c['pc'], 16), int(c['target'], 16))
                           for c in cfg['calls'] if not c.get('indirect'))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('invalid CFG call records') from exc
    actual = Counter(decode_bl_sites(info['text'], info['text_address'], start, end))
    if recorded != actual:
        missing = list((actual - recorded).elements())
        extra = list((recorded - actual).elements())
        raise ValueError(f'CFG direct BL mismatch: missing={missing[:5]}, extra={extra[:5]}')
    return len(actual)


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
        if not re.search(r'extern\s+"C"\s+[^;{}]+\brecovered_' + format(addr, 'x') + r'\s*\([^;{}]*\)\s*\{', source_text):
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
        'dependency_closure_complete': (counts['missing_internal_cpp'] == 0 and counts['indirect_unresolved'] == 0),
        'native_link_tested': False,
        'complete': False,
        'limitations': 'Source-blind structural dependency audit only; generated files are not proof of valid ABI, behavioral equivalence, or an executable game.'
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cfg', required=True, type=Path)
    p.add_argument('--elf', type=Path, help='independently verify every CFG direct BL against stripped ELF')
    p.add_argument('--generated-dir', required=True, type=Path)
    p.add_argument('--expected-sha256')
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--require-dependency-closure', action='store_true',
                   help='exit nonzero if any internal call is missing or indirect unresolved')
    args = p.parse_args()
    cfg = json.loads(args.cfg.read_text())
    if args.elf is not None:
        verify_cfg_against_elf(cfg, args.elf)
    result = audit(cfg, generated_functions(args.generated_dir), args.expected_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['call_sites']} call sites; {result['calls_to_generated_cpp']} generated C++; "
          f"{result['calls_to_external_plt']} external PLT; "
          f"{result['calls_missing_internal_cpp']} missing internal calls "
          f"({', '.join(result['missing_internal_targets'])}); not executable")
    if args.require_dependency_closure and not result['dependency_closure_complete']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
