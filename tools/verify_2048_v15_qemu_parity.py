#!/usr/bin/env python3
"""Fail-closed verifier for EdgeAI V15 original AArch64 versus generated C++.

TSV hashes were pinned from source-blind C++ BEFORE original ARM64 QEMU.
Passing only --cpp-binary does not prove ARM64 parity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ELF_SHA = 'a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b'
CPP_SHA = 'b43bba39aeafbb9375be3f852e16e801b15ed59c32d069b25874386eb66337c5'
HEX64 = re.compile(r'[0-9a-f]{64}\Z')


def parse_cases(path):
    lines = Path(path).read_text(encoding='ascii').splitlines()
    if len(lines) != 22 or lines[:2] != [f'# ELF sha256: {ELF_SHA}',
                                        f'# Generated C++ sha256: {CPP_SHA}']:
        raise ValueError('wrong case count or unpinned ELF/C++ provenance')
    cases = []
    for line in lines[2:]:
        fields = line.split('\t')
        if len(fields) != 3 or not HEX64.fullmatch(fields[2]):
            raise ValueError('invalid case record')
        seq, size, digest = fields
        if not re.fullmatch(r'[0-9]+(?::[0-9]+)*', seq):
            raise ValueError('invalid score sequence')
        values = [int(x) for x in seq.split(':')]
        if not 1 <= len(values) <= 256 or any(x > 0xffffffff for x in values):
            raise ValueError('score outside uint32 range')
        if not size.isdecimal() or int(size) <= 0:
            raise ValueError('invalid expected byte count')
        cases.append((values, int(size), digest))
    return cases


def verify_bytes(data, expected_size, expected_sha, context):
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != expected_size or digest != expected_sha:
        raise AssertionError(f'{context}: stdout mismatch: {len(data)} bytes / {digest}')


def verify(cases_path, original_dir=None, cpp_binary=None):
    if not original_dir and not cpp_binary:
        raise ValueError('provide --original-dir or --cpp-binary')
    cases = parse_cases(cases_path)
    if original_dir:
        root = Path(original_dir)
        found = {p.name for p in root.glob('original_case_*.bin')}
        expected = {f'original_case_{i:02d}.bin' for i in range(len(cases))}
        if found != expected:
            raise ValueError(f'original ARM64 output set incomplete/extra: {len(found)} files')
    total = 0
    for i, (values, expected_size, digest) in enumerate(cases):
        if original_dir:
            data = (Path(original_dir) / f'original_case_{i:02d}.bin').read_bytes()
            verify_bytes(data, expected_size, digest, f'original ARM64 case {i}')
        if cpp_binary:
            cmd = [str(Path(cpp_binary).resolve()), *map(str, values)]
            data = subprocess.check_output(cmd, timeout=20)
            verify_bytes(data, expected_size, digest, f'generated C++ case {i}')
        total += expected_size
    return {'cases': len(cases), 'calls': sum(len(x[0]) for x in cases),
            'stdout_bytes': total, 'original_arm64_raw_outputs_checked': bool(original_dir),
            'generated_cpp_checked': bool(cpp_binary), 'mismatches': 0,
            'elf_sha256': ELF_SHA, 'cpp_source_sha256': CPP_SHA}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--original-dir', type=Path)
    p.add_argument('--cpp-binary', type=Path)
    args = p.parse_args()
    print(json.dumps(verify(args.cases, args.original_dir, args.cpp_binary), indent=2))


if __name__ == '__main__':
    main()
