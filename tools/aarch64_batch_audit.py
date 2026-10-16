#!/usr/bin/env python3
"""Batch read-only AArch64 function evidence with bounded disassembly.

Gathers compiler/LLVM cross-referenced static CFG and table-base candidate
inventories for selected named ELF functions. This is not runtime reachability,
a decompiler, or proof of arbitrary ELF instruction semantics.
"""
import argparse
from collections import Counter
import hashlib
import json
import mmap
from pathlib import Path
import re
import shutil
import subprocess

from elf_inspect import inspect
from aarch64_branch_map import analyze as scan_function
from aarch64_cfg import build_graph
from aarch64_indirect_audit import analyze as indirect_audit
from aarch64_cfg_provenance import analyze as dataflow_audit

MAX_FILE_BYTES = 320 * 1024 * 1024
MAX_FUNCTIONS = 64
MAX_DISASM_BYTES = 8 * 1024 * 1024
MAX_FUNCTION_SIZE = 1024 * 1024
ELF_MAGIC = b'\x7fELF\x02\x01\x01'


def _get_disassembly(path, start, size, timeout=40):
    executable = shutil.which('llvm-objdump')
    if not executable:
        raise RuntimeError('llvm-objdump not installed')
    args = [executable, '--no-show-raw-insn', '-d',
            '--start-address=' + hex(start),
            '--stop-address=' + hex(start + size), str(path)]
    # Do not execute binaries being inspected; use the LLVM decoder only.
    try:
        process = subprocess.run(args, check=False, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('LLVM disassembly timeout') from exc
    if process.returncode:
        raise RuntimeError('llvm-objdump failed: ' + process.stderr[:200].decode(errors='replace'))
    if len(process.stdout) > MAX_DISASM_BYTES:
        raise RuntimeError('LLVM disassembly exceeds byte budget')
    result = process.stdout.decode('utf-8', errors='replace')
    if not re.search(r'^\s*[a-fA-F0-9]+:\s+[A-Za-z]', result, re.M):
        raise RuntimeError('no LLVM instruction lines in selected function')
    return result


def _summarize_function(data, path, name, declared_size):
    scan = scan_function(data, name, max_results=1000)
    if scan['sample_truncated'] or scan['size_bytes'] != declared_size:
        return {'function': name, 'status': 'SKIPPED_TRUNCATED_CONTROL_SCAN',
                'size_bytes': declared_size, 'control_transfers': scan['decoded_control_transfers']}
    graph = build_graph(scan)
    disasm = _get_disassembly(path, int(scan['entry'], 16), declared_size)
    indirect = indirect_audit(scan, disasm)
    provenance = dataflow_audit(graph, indirect, disasm)
    if provenance['site_count'] != indirect['indirect_site_count']:
        raise ValueError('site count disagreement')
    counts = Counter(site['status'] for site in provenance['sites'])
    return {
        'function': name, 'status': 'STATIC_AUDIT_COMPLETED',
        'entry': scan['entry'], 'size_bytes': declared_size,
        'decoded_control_transfers': scan['decoded_control_transfers'],
        'basic_blocks': graph['block_count'],
        'partially_reachable_blocks': graph['candidate_entry_reachable_blocks'],
        'indirect_sites': indirect['indirect_site_count'],
        'table_pattern_candidates': indirect['pattern_counts'].get(
            'pc_relative_indexed_table_dispatch_candidate', 0),
        'common_base_candidates': provenance['static_cfg_base_candidates'],
        'provenance_status_counts': dict(sorted(counts.items())),
        'site_evidence': provenance['sites'],
        'runtime_paths_proven': False,
        'table_targets_resolved': False,
    }


def run(path, names=(), max_functions=20, min_size=4):
    """Audit a deterministic subset of symbols, never execute target code."""
    path = Path(path)
    if not 1 <= max_functions <= MAX_FUNCTIONS:
        raise ValueError('max_functions must be 1..64')
    if not 4 <= min_size <= MAX_FUNCTION_SIZE or min_size % 4:
        raise ValueError('min_size must be aligned and bounded')
    file_size = path.stat().st_size
    if not 64 <= file_size <= MAX_FILE_BYTES:
        raise ValueError('ELF file exceeds configured bounds')
    with path.open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if data[:7] != ELF_MAGIC:
            raise ValueError('expected little endian ELF64')
        info = inspect(data)
        if info.get('bits') != 64 or info.get('machine') != 183:
            raise ValueError('expected AArch64 ELF64')
        candidates = {}
        for sym in info['functions']:
            name = sym['name']
            size = sym['size']
            if not name or not isinstance(size, int) or size < min_size or size > MAX_FUNCTION_SIZE or size % 4:
                continue
            if names and name not in names:
                continue
            # Duplicate symbol names make independent audits ambiguous.
            if name in candidates:
                candidates[name] = None
            else:
                candidates[name] = sym
        if names:
            missing = set(names) - {name for name, sym in candidates.items() if sym is not None}
            if missing:
                raise ValueError('requested function missing, ambiguous or outside budget: ' + ', '.join(sorted(missing)))
        valid = [(name, sym) for name, sym in candidates.items() if sym is not None]
        valid.sort(key=lambda item: (-item[1]['size'], item[0]))
        valid = valid[:max_functions]
        results = []
        for name, sym in valid:
            try:
                results.append(_summarize_function(data, path, name, sym['size']))
            except (ValueError, KeyError, TypeError, RuntimeError) as exc:
                # One unsupported function never contaminates evidence for another.
                results.append({'function': name, 'status': 'UNSUPPORTED',
                                'size_bytes': sym['size'],
                                'reason': type(exc).__name__ + ': ' + str(exc)[:200]})
        completed = [x for x in results if x['status'] == 'STATIC_AUDIT_COMPLETED']
        totals = {
            'functions_selected': len(valid), 'functions_completed': len(completed),
            'functions_unsupported_or_skipped': len(results) - len(completed),
            'instructions_in_completed_functions': sum(x['size_bytes'] // 4 for x in completed),
            'blocks_in_completed_functions': sum(x['basic_blocks'] for x in completed),
            'partial_entry_reachable_blocks': sum(x['partially_reachable_blocks'] for x in completed),
            'indirect_sites_in_completed_functions': sum(x['indirect_sites'] for x in completed),
            'table_patterns_in_completed_functions': sum(x['table_pattern_candidates'] for x in completed),
            'common_base_candidates_in_completed_functions': sum(x['common_base_candidates'] for x in completed),
        }
        return {
            'status': 'EDGEAI_AARCH64_STATIC_BATCH_AUDIT',
            'file_sha256': hashlib.sha256(data).hexdigest(),
            'file_size_bytes': file_size, 'architecture': 'AArch64',
            'selection': {'exact_names': list(names), 'max_functions': max_functions, 'min_size_bytes': min_size},
            'summary': totals, 'functions': results,
            'target_executed': False, 'runtime_paths_proven': False,
            'sources': 'ELF bytes, named function symbols and bounded LLVM disassembly',
            'limitations': [
                'Only unambiguous ELF named functions are selected; stripped symbols require separate address-based workflow.',
                'A static branch pattern is not runtime reachability or decompilation.',
                'Unknown indirect predecessors and entry points can invalidate candidate paths.',
                'No game state, original source, or behavior is recovered.',
            ],
        }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--function', action='append', dest='functions', default=[],
                   help='Exact ELF symbol name; repeat to select multiple')
    p.add_argument('--max-functions', type=int, default=20)
    p.add_argument('--min-size', type=int, default=4)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)
    report = run(args.elf, tuple(args.functions), args.max_functions, args.min_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report['summary'], indent=2, sort_keys=True))
    return report


if __name__ == '__main__':
    main()
