#!/usr/bin/env python3
"""Regenerate and audit the source-blind 2048 V15 C++ providers, fail closed.

Never substitutes a mock or callback wrapper for an original function. A successful
host-native link is NOT proof of ARM64 equivalence or whole-game reconstruction.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from edgeai_2048_bundle_verify import verify

PINNED_ELF_SHA256 = 'a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b'
NAME = re.compile(r'candidate_([0-9a-fA-F]+)\.cpp\Z')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def run_command(args, timeout):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'command unavailable or timed out: {args[0]}: {exc}') from exc
    if p.returncode:
        raise RuntimeError(f'command failed (exit {p.returncode}): {args[0]}: {(p.stderr or p.stdout)[-1400:]}')
    return p


def rebuild(elf, destination, tool_dir, expected_count=19,
            expected_elf_sha256=PINNED_ELF_SHA256, timeout=180):
    elf, destination, tool_dir = Path(elf).resolve(), Path(destination).resolve(), Path(tool_dir).resolve()
    if not elf.is_file():
        raise ValueError('ELF not found')
    digest = sha256(elf)
    if digest != expected_elf_sha256:
        raise ValueError(f'ELF SHA-256 mismatch: got {digest}, expected {expected_elf_sha256}')
    if expected_count < 1:
        raise ValueError('expected_count must be positive')
    if destination.exists():
        raise FileExistsError(f'destination already exists (will not overwrite): {destination}')
    if not destination.parent.is_dir():
        raise ValueError('destination parent directory does not exist')
    generator = tool_dir / 'aarch64_multistage_batch.py'
    gate = tool_dir / 'edgeai_cpp_link_gate.py'
    if not generator.is_file() or not gate.is_file():
        raise FileNotFoundError('required generator or native link gate is missing')
    with tempfile.TemporaryDirectory(prefix='.edgeai-v15-stage-', dir=destination.parent) as td:
        stage = Path(td) / 'bundle'
        stage.mkdir()
        run_command([sys.executable, str(generator), str(elf), '--output-dir', str(stage),
                     '--enable-stateful-printf'], timeout)
        coverage_path = stage / 'coverage.json'
        if not coverage_path.is_file():
            raise RuntimeError('generator did not produce coverage.json')
        coverage = json.loads(coverage_path.read_text(encoding='utf-8'))
        if coverage.get('binary_sha256') != digest:
            raise RuntimeError('generator reported a different ELF hash')
        if coverage.get('source_read') is not False or coverage.get('symbols_used') is not False:
            raise RuntimeError('source-blind provenance is missing or contradicted')
        if coverage.get('compile_status') != 'SUCCEEDED':
            raise RuntimeError(f"generated library failed: {coverage.get('compile_status')}")
        if coverage.get('cpp_emitted_candidate_count') != expected_count:
            raise RuntimeError('generated candidate count differs from expected')
        sources = sorted(stage.glob('candidate_*.cpp'))
        addresses = set()
        for source in sources:
            m = NAME.fullmatch(source.name)
            if not m:
                raise RuntimeError(f'invalid generated filename: {source.name}')
            address = int(m.group(1), 16)
            if address in addresses:
                raise RuntimeError(f'duplicate address: {address:#x}')
            addresses.add(address)
        if len(sources) != expected_count:
            raise RuntimeError('actual source count differs from expected')
        report_addresses = {int(row['address'], 16) for row in coverage.get('functions', [])
                            if row.get('status') != 'UNSUPPORTED'}
        if addresses != report_addresses:
            raise RuntimeError('generated source addresses do not match coverage.json')
        native_path = stage / 'native_link.json'
        run_command([sys.executable, str(gate), '--generated-dir', str(stage),
                     '--strict-link', '--output', str(native_path)], timeout)
        native = json.loads(native_path.read_text(encoding='utf-8'))
        if (not native.get('passed') or not native.get('all_exports_verified')
                or not native.get('strict_link', {}).get('passed')
                or native.get('candidate_count') != expected_count):
            raise RuntimeError('native export/link gate did not prove closure')
        manifest = {
            'schema_version': 2, 'elf_sha256': digest,
            'generated_candidates': expected_count,
            'source_blind_provenance': True,
            'native_host_link_verified': True,
            'arm64_qemu_parity_tested_in_this_run': False,
            'whole_game_recovered': False,
            'files': {p.name: sha256(p) for p in [*sources, coverage_path, native_path, stage / 'recovered_candidates.so']},
            'limitations': 'Host-native C++ linkage only; not ARM64/QEMU or full-game parity.'
        }
        (stage / 'bundle_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        verify(stage, elf)
        # Atomic publish: no partial output directory is exposed on failure.
        os.rename(stage, destination)
        return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--destination', required=True, type=Path)
    p.add_argument('--tool-dir', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--timeout', type=int, default=180)
    a = p.parse_args()
    try:
        result = rebuild(a.elf, a.destination, a.tool_dir, timeout=a.timeout)
    except (ValueError, FileNotFoundError, FileExistsError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f'RECOVERY BLOCKED: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
