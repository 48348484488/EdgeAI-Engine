#!/usr/bin/env python3
"""Independent after-the-fact symbol oracle for a stripped-only AArch64 scan.

Use the unstripped ELF only *after* generation of the candidate report.
Never import its names into the algorithm that discovers boundaries.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

from aarch64_stripped_discovery import load_text

# Read-only runtime symbol exclusions for the explicit 2048 benchmark. These
# are not an input to the stripped entry detection algorithm.
STARTUP_ONLY = {'_start', '_dl_relocate_static_pie', 'call_weak_fn'}
FUNC_RE = re.compile(r'^\s*\d+:\s+([0-9a-fA-F]+)\s+(\d+)\s+FUNC\s+'
                     r'(?:LOCAL|GLOBAL|WEAK)\s+\S+\s+(\d+)\s+(.+)$', re.M)


def check(stripped_path, symbol_path, scan_path):
    stripped = load_text(stripped_path)
    oracle = load_text(symbol_path)
    if stripped['text_address'] != oracle['text_address'] or stripped['text'] != oracle['text']:
        raise ValueError('ELF executable code changed between stripped and symbol oracle')
    scan = json.loads(Path(scan_path).read_text())
    if scan['input_sha256'] != stripped['sha256'] or scan['symbols_used'] or scan['source_read']:
        raise ValueError('candidate report not from stripped source-blind ELF')
    output = subprocess.run(['readelf', '-Ws', str(symbol_path)], capture_output=True,
                            check=True, text=True).stdout
    lo, hi = stripped['text_address'], stripped['text_address'] + len(stripped['text'])
    ground_truth = {}
    for m in FUNC_RE.finditer(output):
        addr, size, ndx, name = int(m[1], 16), int(m[2]), int(m[3]), m[4].strip()
        if lo <= addr < hi and size >= 4:
            ground_truth[addr] = name
    if len(ground_truth) < 1:
        raise ValueError('oracle has no defined functions')
    pred = {int(item['address'], 16) for item in scan['candidate_entries']}
    game = {pc: name for pc, name in ground_truth.items() if name not in STARTUP_ONLY}
    if not game:
        raise ValueError('zero game functions after runtime exclusions')
    return {
        'game': 'Frost-Phoenix/2048-cli',
        'upstream_commit': '53f4da8249cbe9bce17e0daefbd7903f4a4684be',
        'target_arch': 'AArch64',
        'source_used_in_entry_discovery': False,
        'recovered_cpp_functions': 0,
        'binary_executed': False,
        'input_stripped_sha256': stripped['sha256'],
        'symbol_oracle_sha256': oracle['sha256'],
        'oracle_access': 'post-analysis only',
        'oracle_filter': 'Defined, nonzero-sized .text FUNC except explicit startup-only symbols',
        'runtime_exclusions': sorted(STARTUP_ONLY),
        'all_nonzero_named_text_functions': len(ground_truth),
        'matched_all_nonzero_named_text_functions': len(ground_truth.keys() & pred),
        'game_named_text_functions': len(game),
        'matched_game_named_text_functions': len(game.keys() & pred),
        'game_named_entry_recall_percent': round(100 * len(game.keys() & pred) / len(game), 2),
        'all_named_function_misses': [{'name': ground_truth[p], 'entry': hex(p)}
                                      for p in sorted(ground_truth.keys() - pred)],
        'unmatched_entry_candidates': [hex(p) for p in sorted(pred - ground_truth.keys())],
        'candidate_count': len(pred),
        'instruction_slots_scanned': scan['instruction_slots_scanned'],
        'limitations': [
            'Entry candidate recognition is not decompilation or semantic correctness.',
            'Match compares entry addresses against named functions, not unknown hidden functions.',
            'Game-vs-runtime classification uses an explicit after-the-fact binary symbol filter.',
            'No equivalent C++ implementation or gameplay validation yet.',
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stripped', required=True, type=Path)
    p.add_argument('--symbols', required=True, type=Path)
    p.add_argument('--candidates', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    results = check(a.stripped, a.symbols, a.candidates)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
