#!/usr/bin/env python3
"""Compile ARM source, recover winner from ELF alone, differential-test its C++."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from recover_winner import recover, emit_cpp
from recover_winner_stripped import recover_stripped
from recover_winner_variants import recover_variants

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'examples' / 'reverse' / 'tictactoe.c'
HARNESS = ROOT / 'tests' / 'winner_differential_harness.cpp'


def execute(args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def validate(source=SOURCE, harness=HARNESS, output=ROOT/'results/winner_reconstruction_test.json',
             candidate_output=ROOT/'results/winner_candidate.cpp', strip_symbols=False, optimization='1'):
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        original_elf = temp/'original_arm.elf'
        execute(['clang', '--target=armv7-none-eabi', '-marm', '-O'+optimization, '-fno-inline',
                 '-nostdlib', '-fuse-ld=lld', '-Wl,-Ttext=0x1000', '-Wl,-e,start',
                 str(source), '-o', str(original_elf)])
        evidence_elf = original_elf
        if strip_symbols:
            evidence_elf = temp/'game_stripped.elf'
            execute(['llvm-objcopy', '--strip-all', str(original_elf), str(evidence_elf)])
        extracted = recover_variants(evidence_elf) if strip_symbols else recover(original_elf)
        candidate = temp/'winner.cpp'
        candidate.write_text(emit_cpp(extracted), encoding='utf-8')
        candidate_arm = temp/'candidate_arm.o'
        execute(['clang++', '--target=armv7-none-eabi', '-marm', '-O1',
                 '-ffreestanding', '-fno-exceptions', '-fno-rtti', '-c',
                 str(candidate), '-o', str(candidate_arm)])
        original_native = temp/'original.o'
        reconstructed_native = temp/'reconstructed.o'
        runner = temp/'runner'
        execute(['clang', '-std=c11', '-O1', '-Dwinner=original_winner',
                 '-Dplay=original_play', '-Dstart=original_start', '-c',
                 str(source), '-o', str(original_native)])
        execute(['clang++', '-std=c++17', '-O1', '-c', str(candidate), '-o', str(reconstructed_native)])
        execute(['clang++', '-std=c++17', '-O1', str(harness), str(original_native),
                 str(reconstructed_native), '-o', str(runner)])
        behavior = json.loads(execute([str(runner)]))
        report = {
            'reference': 'ARM32 ELF compiled from test game C',
            'function': 'winner',
            'extraction': extracted,
            'stripped_elf_tested': strip_symbols,
            'reference_arm_optimization': '-O'+optimization,
            'arm_candidate_compiled': candidate_arm.is_file(),
            'native_differential': behavior,
            'comparisons': {'all_four_value_boards': 262144, 'uniform_extreme_boards': 4,
                            'deterministic_full_width_boards': 65536},
            'original_source_used_for_generation': False,
            'original_source_used_for_differential_reference': True,
            'byte_for_byte_identity_tested': False,
            'qemu_arm_tested': False,
            'limitations': ('ELF still has symbol names; winner structure and equality/zero test '
                            'recognized from one clang ARM -O1 pattern, not general autonomous C++ recovery')
        }
        if not behavior['passed'] or behavior['tested_cases'] != 327684:
            raise AssertionError('winner candidate did not pass differential test')
        output = Path(output)
        candidate_output = Path(candidate_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        candidate_output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        candidate_output.write_text(candidate.read_text(encoding='utf-8'), encoding='utf-8')
        print(json.dumps({'tested_cases': behavior['tested_cases'],
                          'mismatches': behavior['mismatches'],
                          'recovered_rows': extracted['loop_iterations'],
                          'arm32_candidate_compiled': report['arm_candidate_compiled']}, indent=2))
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--strip', action='store_true', help='Remove all symbols before recovering winner')
    parser.add_argument('--optimization', choices=['1','2','3','s','z'], default='1', help='Clang ARM optimization for compiled reference')
    parser.add_argument('--harness', type=Path, default=HARNESS)
    parser.add_argument('--output', type=Path, default=ROOT/'results/winner_reconstruction_test.json')
    parser.add_argument('--candidate-output', type=Path, default=ROOT/'results/winner_candidate.cpp')
    args = parser.parse_args()
    validate(args.source, args.harness, args.output, args.candidate_output, args.strip, args.optimization)
