#!/usr/bin/env python3
"""Independent integrity gate for an EdgeAI source-blind 2048 V15 bundle.

Checks the *published bytes*, not merely the generator's success flag.
Integrity and native link closure are not proof of ARM64 behavioral parity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

CANDIDATE = re.compile(r'candidate_([0-9a-fA-F]+)\.cpp\Z')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
ARTIFACTS = ('coverage.json', 'native_link.json', 'recovered_candidates.so')
EXPORT = re.compile(r'^recovered_([0-9a-f]+)

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def safe_file(root, name):
    if not isinstance(name, str) or name in ('', '.', '..') or Path(name).name != name:
        raise ValueError(f'unsafe bundle filename: {name!r}')
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'missing or symlinked bundle file: {name}')
    return path


def verify(root, elf=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('bundle directory not found')
    manifest = json.loads(safe_file(root, 'bundle_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 2:
        raise ValueError('expected bundle manifest schema version 2')
    count = manifest.get('generated_candidates')
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError('invalid candidate count')
    elf_sha = manifest.get('elf_sha256')
    if not isinstance(elf_sha, str) or not DIGEST.fullmatch(elf_sha):
        raise ValueError('invalid original ELF SHA-256')
    if elf is not None and digest(Path(elf)) != elf_sha:
        raise ValueError('original ELF digest mismatch')
    if (manifest.get('source_blind_provenance') is not True or
            manifest.get('native_host_link_verified') is not True or
            manifest.get('arm64_qemu_parity_tested_in_this_run') is not False or
            manifest.get('whole_game_recovered') is not False):
        raise ValueError('unverified or misleading manifest claims')
    files = manifest.get('files')
    if not isinstance(files, dict) or len(files) != count + len(ARTIFACTS):
        raise ValueError('manifest file set/count mismatch')
    names = sorted(p.name for p in root.glob('candidate_*.cpp'))
    if len(names) != count or len(set(names)) != count:
        raise ValueError('actual candidate count mismatch')
    expected_names = set(names) | set(ARTIFACTS)
    if set(files) != expected_names:
        raise ValueError('missing, extra, or untracked bundle files')
    addresses = set()
    for name in names:
        match = CANDIDATE.fullmatch(name)
        if not match:
            raise ValueError(f'invalid candidate name: {name}')
        address = int(match.group(1), 16)
        if address in addresses:
            raise ValueError(f'duplicate address: {address:#x}')
        addresses.add(address)
    for name, expected in files.items():
        if not isinstance(expected, str) or not DIGEST.fullmatch(expected):
            raise ValueError(f'invalid digest for {name}')
        if digest(safe_file(root, name)) != expected:
            raise ValueError(f'file digest mismatch: {name}')
    if safe_file(root, 'recovered_candidates.so').stat().st_size == 0:
        raise ValueError('empty compiled library')
    coverage = json.loads(safe_file(root, 'coverage.json').read_text(encoding='utf-8'))
    if (coverage.get('binary_sha256') != elf_sha or
            coverage.get('source_read') is not False or
            coverage.get('symbols_used') is not False or
            coverage.get('compile_status') != 'SUCCEEDED' or
            coverage.get('cpp_emitted_candidate_count') != count):
        raise ValueError('coverage provenance/count/compile mismatch')
    selected = coverage.get('functions')
    if not isinstance(selected, list):
        raise ValueError('coverage functions missing')
    covered = [int(r['address'], 16) for r in selected if r.get('status') != 'UNSUPPORTED']
    if len(covered) != count or set(covered) != addresses:
        raise ValueError('coverage addresses do not match C++ sources')
    native = json.loads(safe_file(root, 'native_link.json').read_text(encoding='utf-8'))
    if (native.get('passed') is not True or
            native.get('all_exports_verified') is not True or
            native.get('candidate_count') != count or
            native.get('strict_link', {}).get('attempted') is not True or
            native.get('strict_link', {}).get('passed') is not True):
        raise ValueError('native link closure not verified')
    rows = native.get('candidates')
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError('native symbol rows missing')
    row_addresses = set()
    for row in rows:
        address = int(row['address'], 16)
        name = f'candidate_{address:x}.cpp'
        if (address in row_addresses or name not in files or row.get('file') != name or
                row.get('expected_export') != f'recovered_{address:x}' or
                row.get('sha256') != files[name] or
                row.get('compiled') is not True or row.get('export_defined') is not True):
            raise ValueError('native export evidence differs from published source')
        row_addresses.add(address)
    if row_addresses != addresses:
        raise ValueError('native export address set mismatch')
    actual_exports = inspect_native_exports(safe_file(root, 'recovered_candidates.so'),
                                            {f'recovered_{a:x}' for a in addresses})
    return {'passed': True, 'candidate_count': count, 'elf_sha256': elf_sha,
            'files_verified': len(files), 'native_exports_verified_from_elf': len(actual_exports),
            'native_host_only': True,
            'arm64_qemu_parity_tested_in_this_run': False,
            'whole_game_recovered': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--elf', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.bundle, args.elf), indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'BUNDLE REJECTED: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
)


def inspect_native_exports(library, expected):
    """Read actual dynamic ELF symbols; never trust a re-hashed JSON assertion."""
    try:
        proc = subprocess.run(['nm', '-D', str(library)], capture_output=True,
                              text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f'native symbol inspection unavailable: {exc}') from exc
    if proc.returncode:
        raise ValueError(f'native library is invalid or unreadable: {proc.stderr[-400:]}')
    defined = set()
    undefined = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        kind, symbol = parts[-2:]
        if not EXPORT.fullmatch(symbol):
            continue
        if kind in ('T', 'W'):
            defined.add(symbol)
        elif kind == 'U':
            undefined.add(symbol)
        else:
            raise ValueError(f'native export has invalid symbol type: {symbol} ({kind})')
    if undefined or defined != expected:
        raise ValueError(f'native ELF export mismatch: missing={sorted(expected-defined)}, '
                         f'extra={sorted(defined-expected)}, unresolved={sorted(undefined)}')
    return sorted(defined)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def safe_file(root, name):
    if not isinstance(name, str) or name in ('', '.', '..') or Path(name).name != name:
        raise ValueError(f'unsafe bundle filename: {name!r}')
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'missing or symlinked bundle file: {name}')
    return path


def verify(root, elf=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError('bundle directory not found')
    manifest = json.loads(safe_file(root, 'bundle_manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 2:
        raise ValueError('expected bundle manifest schema version 2')
    count = manifest.get('generated_candidates')
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError('invalid candidate count')
    elf_sha = manifest.get('elf_sha256')
    if not isinstance(elf_sha, str) or not DIGEST.fullmatch(elf_sha):
        raise ValueError('invalid original ELF SHA-256')
    if elf is not None and digest(Path(elf)) != elf_sha:
        raise ValueError('original ELF digest mismatch')
    if (manifest.get('source_blind_provenance') is not True or
            manifest.get('native_host_link_verified') is not True or
            manifest.get('arm64_qemu_parity_tested_in_this_run') is not False or
            manifest.get('whole_game_recovered') is not False):
        raise ValueError('unverified or misleading manifest claims')
    files = manifest.get('files')
    if not isinstance(files, dict) or len(files) != count + len(ARTIFACTS):
        raise ValueError('manifest file set/count mismatch')
    names = sorted(p.name for p in root.glob('candidate_*.cpp'))
    if len(names) != count or len(set(names)) != count:
        raise ValueError('actual candidate count mismatch')
    expected_names = set(names) | set(ARTIFACTS)
    if set(files) != expected_names:
        raise ValueError('missing, extra, or untracked bundle files')
    addresses = set()
    for name in names:
        match = CANDIDATE.fullmatch(name)
        if not match:
            raise ValueError(f'invalid candidate name: {name}')
        address = int(match.group(1), 16)
        if address in addresses:
            raise ValueError(f'duplicate address: {address:#x}')
        addresses.add(address)
    for name, expected in files.items():
        if not isinstance(expected, str) or not DIGEST.fullmatch(expected):
            raise ValueError(f'invalid digest for {name}')
        if digest(safe_file(root, name)) != expected:
            raise ValueError(f'file digest mismatch: {name}')
    if safe_file(root, 'recovered_candidates.so').stat().st_size == 0:
        raise ValueError('empty compiled library')
    coverage = json.loads(safe_file(root, 'coverage.json').read_text(encoding='utf-8'))
    if (coverage.get('binary_sha256') != elf_sha or
            coverage.get('source_read') is not False or
            coverage.get('symbols_used') is not False or
            coverage.get('compile_status') != 'SUCCEEDED' or
            coverage.get('cpp_emitted_candidate_count') != count):
        raise ValueError('coverage provenance/count/compile mismatch')
    selected = coverage.get('functions')
    if not isinstance(selected, list):
        raise ValueError('coverage functions missing')
    covered = [int(r['address'], 16) for r in selected if r.get('status') != 'UNSUPPORTED']
    if len(covered) != count or set(covered) != addresses:
        raise ValueError('coverage addresses do not match C++ sources')
    native = json.loads(safe_file(root, 'native_link.json').read_text(encoding='utf-8'))
    if (native.get('passed') is not True or
            native.get('all_exports_verified') is not True or
            native.get('candidate_count') != count or
            native.get('strict_link', {}).get('attempted') is not True or
            native.get('strict_link', {}).get('passed') is not True):
        raise ValueError('native link closure not verified')
    rows = native.get('candidates')
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError('native symbol rows missing')
    row_addresses = set()
    for row in rows:
        address = int(row['address'], 16)
        name = f'candidate_{address:x}.cpp'
        if (address in row_addresses or name not in files or row.get('file') != name or
                row.get('expected_export') != f'recovered_{address:x}' or
                row.get('sha256') != files[name] or
                row.get('compiled') is not True or row.get('export_defined') is not True):
            raise ValueError('native export evidence differs from published source')
        row_addresses.add(address)
    if row_addresses != addresses:
        raise ValueError('native export address set mismatch')
    return {'passed': True, 'candidate_count': count, 'elf_sha256': elf_sha,
            'files_verified': len(files), 'native_host_only': True,
            'arm64_qemu_parity_tested_in_this_run': False,
            'whole_game_recovered': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--elf', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.bundle, args.elf), indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f'BUNDLE REJECTED: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
