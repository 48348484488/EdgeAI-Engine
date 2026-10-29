"""V23 main-loop host regression; does not claim ARM64/QEMU parity."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / 'experiments' / '2048_v23'
if not EXPERIMENT.is_dir():
    EXPERIMENT = ROOT  # portable V23 ZIP layout


class MainLoopV23(unittest.TestCase):
    def test_main_candidate_host_scenarios(self):
        compiler = shutil.which('g++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        with tempfile.TemporaryDirectory() as td:
            executable = Path(td) / 'main-v23-test'
            subprocess.run(
                [compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                 '-pedantic', str(EXPERIMENT / 'test_main_candidate.cpp'), '-o', str(executable)],
                check=True, capture_output=True, text=True, timeout=45)
            run = subprocess.run([str(executable)], check=True, capture_output=True,
                                 text=True, timeout=10)
            self.assertIn('PASS: 8 main-loop scenario checks', run.stdout)

    def test_pinned_elf_if_supplied(self):
        path = os.environ.get('EDGEAI_2048_ELF')
        if not path:
            self.skipTest('set EDGEAI_2048_ELF to run source-blind ELF contract')
        disassembler = shutil.which('llvm-objdump')
        if not disassembler:
            self.skipTest('llvm-objdump unavailable')
        result = subprocess.run(
            ['python3', str(EXPERIMENT / 'verify_main_elf.py'), '--elf', path,
             '--disassembler', disassembler],
            check=True, capture_output=True, text=True, timeout=30)
        self.assertIn('static_contract_verified', result.stdout)


if __name__ == '__main__':
    unittest.main()
