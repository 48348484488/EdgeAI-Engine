#!/usr/bin/env python3
"""Bounded, fail-closed watchdog for source-blind EdgeAI 2048 V15 regeneration.

Reports whether a child actually ran, failed, or timed out. This does not
replace ARM64/QEMU parity checks or establish source equivalence.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

PINNED_ELF_SHA256 = 'a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b'
REQUIRED = ('aarch64_multistage_batch.py', 'edgeai_2048_v15_recovery.py',
            'edgeai_2048_bundle_verify.py', 'edgeai_cpp_link_gate.py')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def local_modules(tool_dir):
    """Trace actual local Python imports; do not mistake a filename list for readiness."""
    root = Path(tool_dir).resolve()
    pending = list(REQUIRED)
    visited = set()
    missing = set()
    while pending:
        filename = pending.pop()
        if filename in visited:
            continue
        visited.add(filename)
        path = root / filename
        if path.is_symlink() or not path.is_file():
            missing.add(filename)
            continue
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            else:
                continue
            for module in modules:
                top = module.split('.')[0]
                if top.startswith(('aarch64_', 'edgeai_')):
                    dep = top + '.py'
                    if dep not in visited:
                        pending.append(dep)
    return sorted(visited), sorted(missing)


def preflight(elf, tool_dir, expected_sha256=PINNED_ELF_SHA256):
    elf = Path(elf)
    if elf.is_symlink() or not elf.is_file():
        raise ValueError('ELF missing or symlinked')
    digest = sha256(elf)
    if digest != expected_sha256:
        raise ValueError(f'ELF SHA-256 mismatch: {digest}')
    modules, missing = local_modules(tool_dir)
    if missing:
        raise ValueError('missing V15 Python modules: ' + ', '.join(missing))
    for executable in ('g++', 'nm'):
        if not shutil.which(executable):
            raise ValueError(f'required native tool missing: {executable}')
    return {'passed': True, 'elf_sha256': digest, 'modules_checked': modules,
            'module_count': len(modules), 'missing_modules': [],
            'native_tools': ['g++', 'nm'], 'qemu_parity_tested': False}


def terminate_group(proc):
    """Reap the leader AND kill descendants, even if the leader already exited.

    On POSIX the driver runs in a new session, so its process-group ID is
    its PID. Checking only proc.poll() misses grandchildren orphaned by a
    driver that exits early. Never kill a group belonging to the caller.
    """
    if os.name == 'posix':
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.02)
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    elif proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def verify_before_publish(stage, elf, tool_dir, expected_sha, deadline):
    """Independently validate published bytes and reproducible C++ linkage.

    A zero exit code and a bundle_manifest.json are not sufficient proof.
    The verification process has its own process group and shares the same
    overall deadline as the generator.
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return 'TIMED_OUT', 'deadline exhausted before independent verification', None
    command = [sys.executable, str(Path(tool_dir).resolve() / 'edgeai_2048_bundle_verify.py'),
               str(stage), '--elf', str(Path(elf).resolve()), '--rebuild-native']
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=(os.name == 'posix'))
    try:
        stdout, stderr = proc.communicate(timeout=remaining)
    except subprocess.TimeoutExpired:
        return 'TIMED_OUT', 'independent verification exceeded total deadline', None
    finally:
        terminate_group(proc)
    if proc.returncode:
        return 'FAILED', 'independent verification rejected bundle: ' + stderr.decode('utf-8', 'replace')[-1200:], None
    try:
        report = json.loads(stdout.decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return 'FAILED', f'independent verifier returned invalid JSON: {exc}', None
    if (report.get('passed') is not True or
            report.get('same_toolchain_rebuild_matched') is not True or
            report.get('elf_sha256') != expected_sha):
        return 'FAILED', 'independent verifier did not attest ELF and native rebuild', None
    return 'PASSED', '', report


def run(elf, destination, tool_dir, timeout=180, heartbeat=5,
        expected_sha256=PINNED_ELF_SHA256, preflight_only=False, on_heartbeat=None):
    if timeout <= 0 or heartbeat <= 0:
        raise ValueError('timeout and heartbeat must be positive')
    start = time.monotonic()
    proof = preflight(elf, tool_dir, expected_sha256)
    if preflight_only:
        return {'status': 'PREFLIGHT_PASSED', 'preflight': proof,
                'regeneration_executed': False, 'qemu_parity_tested': False}
    dest = Path(destination).absolute()
    if dest.exists() or dest.is_symlink():
        raise FileExistsError('destination already exists; refusing overwrite')
    if not dest.parent.is_dir():
        raise ValueError('destination parent directory missing')
    with tempfile.TemporaryDirectory(prefix='.edgeai-v31-', dir=dest.parent) as work:
        work = Path(work)
        staged = work / 'candidate_bundle'
        stdout_path, stderr_path = work / 'stdout.log', work / 'stderr.log'
        command = [sys.executable, str(Path(tool_dir).resolve() / 'edgeai_2048_v15_recovery.py'),
                   str(Path(elf).resolve()), '--destination', str(staged),
                   '--tool-dir', str(Path(tool_dir).resolve()), '--timeout', str(max(1, int(timeout)))]
        with stdout_path.open('wb') as out, stderr_path.open('wb') as err:
            proc = subprocess.Popen(command, stdout=out, stderr=err,
                                    start_new_session=(os.name == 'posix'))
            next_beat = time.monotonic() + heartbeat
            timed_out = False
            try:
                while proc.poll() is None:
                    now = time.monotonic()
                    if now - start >= timeout:
                        timed_out = True
                        terminate_group(proc)
                        break
                    if now >= next_beat:
                        if on_heartbeat:
                            on_heartbeat({'elapsed_seconds': round(now-start, 2),
                                          'pid': proc.pid, 'state': 'RUNNING'})
                        next_beat = now + heartbeat
                    time.sleep(min(0.1, heartbeat / 2, max(0.01, timeout-(now-start))))
            finally:
                terminate_group(proc)
        duration = round(time.monotonic() - start, 3)
        stdout = stdout_path.read_text(encoding='utf-8', errors='replace')[-1600:]
        stderr = stderr_path.read_text(encoding='utf-8', errors='replace')[-1600:]
        if timed_out:
            return {'status': 'TIMED_OUT', 'elapsed_seconds': duration,
                    'exit_code': proc.returncode, 'stderr_tail': stderr,
                    'regeneration_executed': True, 'destination_published': False,
                    'qemu_parity_tested': False}
        if proc.returncode != 0 or not staged.is_dir():
            return {'status': 'FAILED', 'elapsed_seconds': duration,
                    'exit_code': proc.returncode, 'stderr_tail': stderr,
                    'stdout_tail': stdout, 'regeneration_executed': True,
                    'destination_published': False, 'qemu_parity_tested': False}
        if not (staged / 'bundle_manifest.json').is_file():
            return {'status': 'FAILED', 'elapsed_seconds': duration,
                    'exit_code': proc.returncode,
                    'stderr_tail': 'driver produced no bundle_manifest.json',
                    'regeneration_executed': True, 'destination_published': False,
                    'qemu_parity_tested': False}
        status, error, attestation = verify_before_publish(
            staged, elf, tool_dir, proof['elf_sha256'], start + timeout)
        if status != 'PASSED':
            return {'status': status, 'elapsed_seconds': round(time.monotonic() - start, 3),
                    'exit_code': proc.returncode, 'stderr_tail': error,
                    'regeneration_executed': True, 'destination_published': False,
                    'independent_bundle_verification_passed': False,
                    'qemu_parity_tested': False}
        # Both the recovery driver and a fresh independent verifier passed.
        # Publishing into the requested destination is a same-filesystem rename.
        if dest.exists() or dest.is_symlink():
            raise FileExistsError('destination created during verification; refusing overwrite')
        os.rename(staged, dest)
        return {'status': 'SUCCEEDED', 'elapsed_seconds': round(time.monotonic() - start, 3),
                'exit_code': 0, 'regeneration_executed': True,
                'destination_published': True, 'destination': str(dest),
                'independent_bundle_verification_passed': True,
                'native_exports_verified': attestation['native_exports_verified_from_elf'],
                'qemu_parity_tested': False}


def write_report(path, result):
    path = Path(path).absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                     prefix='.edgeai-report-', suffix='.json',
                                     dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        json.dump(result, f, indent=2)
        f.write('\n')
    os.replace(tmp, path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--tool-dir', type=Path, default=Path(__file__).resolve().parent)
    p.add_argument('--destination', type=Path)
    p.add_argument('--report', type=Path)
    p.add_argument('--timeout', type=float, default=180)
    p.add_argument('--heartbeat', type=float, default=5)
    p.add_argument('--preflight-only', action='store_true')
    args = p.parse_args()
    if not args.preflight_only and not args.destination:
        p.error('--destination is required for regeneration')
    try:
        result = run(args.elf, args.destination, args.tool_dir,
                     args.timeout, args.heartbeat, preflight_only=args.preflight_only,
                     on_heartbeat=lambda e: print(json.dumps(e), flush=True))
    except (ValueError, OSError, SyntaxError, UnicodeError) as exc:
        result = {'status': 'BLOCKED', 'error': str(exc),
                  'regeneration_executed': False, 'qemu_parity_tested': False}
    if args.report:
        write_report(args.report, result)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] in ('PREFLIGHT_PASSED', 'SUCCEEDED') else 2


if __name__ == '__main__':
    raise SystemExit(main())
