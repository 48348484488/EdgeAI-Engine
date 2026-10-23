#!/usr/bin/env python3
"""Offline, source-blind EdgeAI CI for the pinned 2048 AArch64 benchmark.

Takes TWO independently archived results, V7 (16 reconstructed functions)
and V12 (five-function QEMU CPU replay), and runs actual tests and C++
generation locally. No GitHub runner, authentication, original game source,
Internet access, or AI GPU is required.

Inputs are exact SHA-256 pinned files, NOT arbitrary ZIPs. Extraction is
bounded and path checked. If any verification fails, exit nonzero.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import time
import zipfile

EXPECTED = {
    'v7': '861d924bca40342a160aa60029aa6d5ddc2841ca087e7ab566790b799667d811',
    'v12': 'a1e21ab10bbd30127ac3f23a0b6b193a36b1f052cdf0bc03083609ae6db7230e',
    'elf': 'a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b',
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def exact_file(path: Path, checksum: str) -> None:
    if not path.is_file() or sha256(path) != checksum:
        raise ValueError(f'input missing or SHA-256 mismatch: {path}')


def safe_unpack(archive: Path, destination: Path, *, max_files=150, max_bytes=18_000_000):
    with zipfile.ZipFile(archive) as zipped:
        files = zipped.infolist()
        if len(files) > max_files or sum(f.file_size for f in files) > max_bytes:
            raise ValueError('archive exceeds file-count or expanded-byte budget')
        for item in files:
            candidate = PurePosixPath(item.filename)
            if (candidate.is_absolute() or not candidate.parts or
                    any(x in ('..', '') for x in candidate.parts) or
                    '\\' in item.filename or '\x00' in item.filename or
                    (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('unsafe ZIP member: ' + repr(item.filename))
            path = destination.joinpath(*candidate.parts)
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(item) as source, path.open('wb') as target:
                    copied = 0
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > max_bytes:
                            raise ValueError('unpacked member exceeds budget')
                        target.write(chunk)


def execute(cmd: list[str], cwd: Path, log_path: Path, timeout: int) -> str:
    started = time.monotonic()
    proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, timeout=timeout)
    log_path.write_text(proc.stdout)
    if proc.returncode:
        raise RuntimeError(f'command exited {proc.returncode}: {cmd!r}; log: {log_path}; tail: {proc.stdout[-1500:]}')
    return f'{time.monotonic() - started:.2f}s'


def run(v7_zip: Path, v12_zip: Path, report: Path, log_dir: Path) -> dict:
    exact_file(v7_zip, EXPECTED['v7'])
    exact_file(v12_zip, EXPECTED['v12'])
    log_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='edgeai-offline-') as temp:
        root = Path(temp)
        v7 = root / 'v7'
        v12 = root / 'v12'
        safe_unpack(v7_zip, v7)
        safe_unpack(v12_zip, v12)
        exact_file(v7 / 'bin/2048-arm64-stripped.elf', EXPECTED['elf'])
        exact_file(v12 / 'original/2048-arm64-stripped.elf', EXPECTED['elf'])

        unit7 = execute([sys.executable, '-m', 'unittest', 'discover', '-p', 'test_aarch64_*.py', '-q'],
                        v7 / 'analysis', log_dir / 'v7_unittest.log', 150)
        unit12 = execute([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test*.py', '-q'],
                         v12, log_dir / 'v12_unittest.log', 80)
        for log, count in ((log_dir / 'v7_unittest.log', 63), (log_dir / 'v12_unittest.log', 20)):
            output = log.read_text()
            require(f'Ran {count} tests' in output and 'OK' in output and 'skipped=' not in output,
                    f'unit tests failed, skipped, or count changed: {log}')
        generated = v7 / 'rebuilt'
        regeneration = execute([sys.executable, 'analysis/aarch64_multistage_batch.py',
                                'bin/2048-arm64-stripped.elf', '--output-dir', str(generated)],
                               v7, log_dir / 'v7_codegen.log', 100)

        coverage = json.loads((generated / 'coverage.json').read_text())
        require(coverage['binary_sha256'] == EXPECTED['elf'], 'wrong regenerated ELF checksum')
        require(coverage['source_read'] is False and coverage['symbols_used'] is False, 'source or symbols were read')
        require(coverage['candidate_entry_count'] == 27, 'candidate entry count changed')
        require(coverage['cpp_emitted_candidate_count'] == 16, 'C++ function coverage changed')
        require(coverage['instructions_emitted'] == 529, 'instruction count changed')
        require(coverage['compile_status'] == 'SUCCEEDED', 'generated C++ did not compile')
        emitted = sorted(generated.glob('candidate_*.cpp'))
        pinned = sorted((v7 / 'batch_v7').glob('candidate_*.cpp'))
        require(len(emitted) == len(pinned) == 16, 'wrong number of generated sources')
        for old, new in zip(pinned, emitted):
            if old.name != new.name or sha256(old) != sha256(new):
                raise ValueError('generated C++ differs from independently pinned V7 file')
        if not (generated / 'recovered_candidates.so').is_file():
            raise ValueError('16-function shared C++ library did not compile')

        replay = execute([sys.executable, 'tools/edgeai_arm64_trace_vm.py',
                          '--manifest', 'replay_manifest.json',
                          '--elf', 'original/2048-arm64-stripped.elf',
                          '--qemu-root', 'qemu', '--report', 'replay_result.json'],
                         v12, log_dir / 'v12_qemu_replay.log', 100)
        machine = json.loads((v12 / 'replay_result.json').read_text())
        require(machine['passed'] is True and machine['function_count'] == 5, 'QEMU CPU parity verification failed')
        require(machine['cases_compared'] == 50 and machine['checks_total'] == 35147, 'QEMU CPU replay coverage changed')
        require(not machine['failed_cases'], 'QEMU CPU replay has failed cases')
        report_data = {
            'status': 'OFFLINE_REGENERATED_AND_TESTED',
            'original_source_used': False,
            'github_actions_runner_required': False,
            'input_sha256': {'v7': EXPECTED['v7'], 'v12': EXPECTED['v12'], 'elf': EXPECTED['elf']},
            'v7': {'test_cases': 63, 'cpp_regenerated_and_compiled': len(emitted),
                   'cpp_sources_byte_identical': True, 'arm64_instructions': 529,
                   'elapsed': {'unit_tests': unit7, 'code_generation': regeneration}},
            'v12': {'test_cases': 20, 'qemu_snapshot_cases_replayed': machine['cases_compared'],
                    'functions': machine['function_count'], 'cpu_and_memory_checks': machine['checks_total'],
                    'differences': len(machine['failed_cases']),
                    'elapsed': {'unit_tests': unit12, 'cpu_replay': replay}},
            'whole_game_decompiled': False,
            'notes': ['Replay uses original QEMU captures, not new live QEMU executions.',
                      'This validates sampled behavior and diagnostic fidelity, not full program equivalence.',
                      'GitHub Actions failures before job steps are not fixed by offline validation.'],
        }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(report_data, indent=2) + '\n')
    return report_data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v7', type=Path, required=True, help='Pinned V7 16-function benchmark ZIP')
    parser.add_argument('--v12', type=Path, required=True, help='Pinned V12 real QEMU trace replay ZIP')
    parser.add_argument('--report', type=Path, default=Path('edgeai_offline_ci_report.json'))
    parser.add_argument('--logs', type=Path, default=Path('edgeai_offline_ci_logs'))
    args = parser.parse_args()
    try:
        result = run(args.v7, args.v12, args.report, args.logs)
    except (ValueError, RuntimeError, AssertionError, OSError, subprocess.TimeoutExpired,
            zipfile.BadZipFile) as error:
        print(f'FAIL: {error}', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
