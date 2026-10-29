#!/usr/bin/env python3
"""Fail-closed native C++ export/link gate for EdgeAI candidate files.

Compiles each candidate and inspects actual ELF object symbols, rather than
searching source text. Optional strict shared linking rejects unresolved symbols.
This checks *host-native* syntax/linkage only, never ARM64/QEMU equivalence.
"""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

NAME = re.compile(r"candidate_([0-9a-fA-F]+)\.cpp\Z")
SYMBOL = re.compile(r"^([0-9a-fA-F]+)?\s*([A-Za-z])\s+(\S+)$")


def command(argv, timeout=45):
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"tool unavailable or timed out: {argv[0]}: {exc}") from exc
    return result


def defined_exports(object_file, nm='nm'):
    result = command([nm, '-g', '--defined-only', str(object_file)])
    if result.returncode:
        raise RuntimeError(f"nm failed: {result.stderr[:800]}")
    exports = {}
    for line in result.stdout.splitlines():
        m = SYMBOL.match(line.strip())
        if m:
            exports[m.group(3)] = m.group(2)
    return exports


def probe(folder, cxx='g++', nm='nm', strict_link=False, timeout=45):
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError('candidate directory does not exist')
    sources = sorted(folder.glob('candidate_*.cpp'))
    if not sources:
        raise ValueError('no candidate sources found')
    entries = []
    seen = set()
    with tempfile.TemporaryDirectory(prefix='edgeai_cpp_gate_') as tmp:
        objects = []
        for source in sources:
            m = NAME.fullmatch(source.name)
            if not m:
                raise ValueError(f'invalid candidate filename: {source.name}')
            addr = int(m.group(1), 16)
            if addr in seen:
                raise ValueError(f'duplicate candidate address: {addr:#x}')
            seen.add(addr)
            obj = Path(tmp) / f'{addr:x}.o'
            result = command([cxx, '-std=c++17', '-O0', '-fPIC', '-c',
                              str(source), '-o', str(obj)], timeout)
            expected = f'recovered_{addr:x}'
            row = {'address': hex(addr), 'file': source.name,
                   'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                   'expected_export': expected, 'compiled': result.returncode == 0,
                   'export_defined': False, 'error': None}
            if result.returncode:
                row['error'] = 'compile: ' + (result.stderr or result.stdout)[-1200:]
            else:
                exports = defined_exports(obj, nm)
                # T = global text, W = weak text; reject variables and undefined symbols.
                row['export_defined'] = exports.get(expected) in ('T', 'W')
                if not row['export_defined']:
                    row['error'] = f'expected unmangled text symbol {expected} not defined'
                objects.append(obj)
            entries.append(row)
        ready = all(r['compiled'] and r['export_defined'] for r in entries)
        link = {'attempted': False, 'passed': False, 'error': None}
        if strict_link and ready:
            result = command([cxx, '-shared', '-Wl,-z,defs',
                              *map(str, objects), '-o', str(Path(tmp) / 'candidates.so')], timeout)
            link['attempted'] = True
            link['passed'] = result.returncode == 0
            if result.returncode:
                link['error'] = 'link: ' + (result.stderr or result.stdout)[-1200:]
        elif strict_link:
            link['error'] = 'skipped: compile/export gate failed'
        return {'candidate_count': len(entries), 'candidates': entries,
                'all_exports_verified': ready, 'strict_link': link,
                'passed': ready and (not strict_link or link['passed']),
                'native_host_only': True, 'arm64_qemu_parity_tested': False,
                'whole_game_recovered': False,
                'limitations': 'Host-native compile/export/link check; not source equivalence, ABI parity, original ARM64 execution, or gameplay validation.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generated-dir', required=True, type=Path)
    p.add_argument('--cxx', default='g++')
    p.add_argument('--nm', default='nm')
    p.add_argument('--strict-link', action='store_true')
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    result = probe(args.generated_dir, args.cxx, args.nm, args.strict_link)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{sum(x['export_defined'] for x in result['candidates'])}/{result['candidate_count']} "
          f"native exports verified; strict link={result['strict_link']['passed']}; "
          f"passed={result['passed']}")
    raise SystemExit(0 if result['passed'] else 2)


if __name__ == '__main__':
    main()
