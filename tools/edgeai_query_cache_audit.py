#!/usr/bin/env python3
"""Audit exact-query cache counters in engine logs; independent of game/architecture.

Accepts log lines containing '<marker> calls=N hits=N misses=N'. This checks
counter consistency and reports observed reuse, NOT a measured FPS speedup.
"""
import argparse
import json
import re
from pathlib import Path

COUNTERS = re.compile(r'\bcalls=(\d+)\s+hits=(\d+)\s+misses=(\d+)\b')


def audit(log: str, marker: str = 'SAMPLE_CACHE', minimum_windows: int = 1) -> dict:
    if not marker or minimum_windows < 0:
        raise ValueError('marker must be nonempty and minimum_windows nonnegative')
    windows, errors = [], []
    for line_number, line in enumerate(log.splitlines(), 1):
        if marker not in line:
            continue
        match = COUNTERS.search(line)
        if match is None:
            errors.append({'line': line_number, 'reason': 'invalid_counters'})
            continue
        calls, hits, misses = map(int, match.groups())
        if calls <= 0 or hits + misses != calls:
            errors.append({'line': line_number, 'reason': 'counter_mismatch'})
            continue
        windows.append({'line': line_number, 'calls': calls, 'hits': hits, 'misses': misses})
    if len(windows) < minimum_windows:
        errors.append({'line': 0, 'reason': 'insufficient_windows'})
    calls = sum(w['calls'] for w in windows)
    hits = sum(w['hits'] for w in windows)
    return {
        'windows': len(windows), 'calls': calls, 'hits': hits,
        'misses': calls - hits, 'hit_ratio': hits / calls if calls else None,
        'violations': errors, 'passed': not errors,
        'fps_improvement_proven': False,
        'original_game_parity_proven': False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--marker', default='SAMPLE_CACHE')
    parser.add_argument('--minimum-windows', type=int, default=1)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = audit(args.log.read_text(encoding='utf-8', errors='replace'),
                   args.marker, args.minimum_windows)
    payload = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding='utf-8')
    print(payload, end='')
    return int(not result['passed'])


if __name__ == '__main__':
    raise SystemExit(main())
