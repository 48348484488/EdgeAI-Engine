#!/usr/bin/env python3
"""Execute winner differential tests in ARM32 Linux under qemu-arm.

Recover a candidate from Clang ARM32 stripped ELF; compile both original and
candidate with GCC ARM Linux. A separate probe reports whether GCC's stripped
ELF can be decoded, without presenting behavioral GCC tests as GCC recovery.
"""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from recover_winner import emit_cpp
from recover_winner_variants import recover_variants
from validate_winner_reconstruction import ROOT, SOURCE, HARNESS

TOOLS = ('clang', 'llvm-objcopy', 'llvm-objdump', 'arm-linux-gnueabihf-gcc',
         'arm-linux-gnueabihf-g++', 'qemu-arm')
OPTIMIZATIONS = ('1', '2', '3', 's', 'z')


def require_toolchain(resolve=shutil.which):
    missing = [tool for tool in TOOLS if resolve(tool) is None]
    if missing:
        raise RuntimeError('ARM32 QEMU test NOT RUN; missing tools: ' + ', '.join(missing))


def execute(args, timeout=120):
    try:
        return subprocess.run(args, check=True, capture_output=True,
                              text=True, timeout=timeout).stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('command failed: ' + ' '.join(map(str, args)) +
                           '\n' + exc.stderr[-3000:]) from exc


def require_linux_arm32(path):
    data = Path(path).read_bytes()[:20]
    if len(data) < 20 or data[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H', data, 18)[0] != 40:
        raise RuntimeError('qemu runner is not a little-endian ARM32 ELF')


def validate(output=ROOT/'results/winner_qemu_arm32.json', optimizations=OPTIMIZATIONS,
             probe_gcc=True):
    require_toolchain()
    records = []
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        probe = {'status': 'not_requested'}
        if probe_gcc:
            gcc_elf = temp/'gcc_reference.elf'
            gcc_stripped = temp/'gcc_reference_stripped.elf'
            try:
                execute(['arm-linux-gnueabihf-gcc', '-marm', '-O1', '-fno-inline',
                         '-nostdlib', '-no-pie', '-Wl,-e,start', str(SOURCE),
                         '-o', str(gcc_elf)])
                execute(['llvm-objcopy', '--strip-all', str(gcc_elf), str(gcc_stripped)])
                try:
                    found = recover_variants(gcc_stripped)
                    probe = {'status': 'recognized', 'pattern': found['optimization_pattern'],
                             'triplets': found['triplets']}
                except ValueError as exc:
                    probe = {'status': 'unsupported_gcc_pattern', 'reason': str(exc)}
            except (RuntimeError, OSError) as exc:
                probe = {'status': 'gcc_probe_failed', 'reason': str(exc)}
        for opt in optimizations:
            if opt not in OPTIMIZATIONS:
                raise ValueError('unsupported Clang optimization: ' + opt)
            arm_elf = temp / ('clang_' + opt + '.elf')
            stripped = temp / ('clang_' + opt + '_stripped.elf')
            cpp = temp / ('candidate_' + opt + '.cpp')
            original_o = temp / ('original_' + opt + '.o')
            candidate_o = temp / ('candidate_' + opt + '.o')
            runner = temp / ('winner_arm32_' + opt)
            execute(['clang', '--target=armv7-none-eabi', '-marm', '-O'+opt,
                     '-fno-inline', '-nostdlib', '-fuse-ld=lld',
                     '-Wl,-Ttext=0x1000', '-Wl,-e,start', str(SOURCE), '-o', str(arm_elf)])
            execute(['llvm-objcopy', '--strip-all', str(arm_elf), str(stripped)])
            recovered = recover_variants(stripped)
            cpp.write_text(emit_cpp(recovered), encoding='utf-8')
            execute(['arm-linux-gnueabihf-gcc', '-marm', '-O1', '-fno-inline',
                     '-Dwinner=original_winner', '-Dplay=original_play',
                     '-Dstart=original_start', '-c', str(SOURCE), '-o', str(original_o)])
            execute(['arm-linux-gnueabihf-g++', '-marm', '-O1', '-std=c++17',
                     '-c', str(cpp), '-o', str(candidate_o)])
            execute(['arm-linux-gnueabihf-g++', '-marm', '-O1', '-std=c++17', '-static',
                     str(HARNESS), str(original_o), str(candidate_o), '-o', str(runner)])
            require_linux_arm32(runner)
            behavior = json.loads(execute(['qemu-arm', str(runner)], timeout=180))
            if not behavior.get('passed') or behavior.get('tested_cases') != 85223 or behavior.get('mismatches') != 0:
                raise RuntimeError('ARM32 QEMU differential divergence for -O' + opt)
            records.append({'clang_arm_source': '-O'+opt,
                            'recognized_pattern': recovered['optimization_pattern'],
                            'arm_linux_compiler': 'GCC ARM (original + candidate + harness)',
                            'runner': 'qemu-arm', 'behavior': behavior})
    result = {'architecture': 'ARM32', 'mode': 'actual_qemu_arm_execution',
              'candidate_source': 'Clang stripped ARM ELF with known winner fingerprint',
              'gcc_binary_recovery_probe': probe,
              'cases': records, 'tested_cases': sum(x['behavior']['tested_cases'] for x in records),
              'mismatches': sum(x['behavior']['mismatches'] for x in records),
              'caveat': 'GCC-produced ARM instructions are only tested behaviorally unless separate probe recognizes them.'}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'tested_cases':result['tested_cases'], 'mismatches':result['mismatches'],
                      'gcc_recovery_probe':probe['status']}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'results/winner_qemu_arm32.json')
    parser.add_argument('--optimizations', default=','.join(OPTIMIZATIONS))
    parser.add_argument('--no-gcc-probe', action='store_true')
    args = parser.parse_args()
    try:
        validate(args.output, tuple(args.optimizations.split(',')), not args.no_gcc_probe)
    except (RuntimeError, ValueError) as exc:
        parser.exit(2, 'ARM validation incomplete: ' + str(exc) + '\n')
