"""Regression tests for true-ELF/QEMU-to-C++ casewise differential comparison.

Set EDGEAI_QEMU_V2_BUNDLE=<unpacked EdgeAI_2048_QEMU_22000_cases_v2
directory> for the real-input tests. This suite must not claim success
when the required original machine artifacts are missing.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from edgeai_qemu_casewise_compare import next_rand,put32,mkboard,check_cases,verify

ROOT=Path(os.environ.get('EDGEAI_QEMU_V2_BUNDLE','/does-not-exist'))
CASES=ROOT/'reference/original_arm64_cases.txt'
MANIFEST=ROOT/'manifest/abi_manifest_v2.json'
ELF=ROOT/'original/2048-arm64-stripped.elf'
LIB=ROOT/'generated/recovered_candidates.so'
MUTANT=ROOT/'negative_control/mutated_winner.so'
AVAILABLE=all(x.is_file() for x in (CASES,MANIFEST,ELF,LIB,MUTANT))


class DeterministicGeneratorTests(unittest.TestCase):
    def test_fixed_board_patterns(self):
        rng=0x31415926
        rng,empty=mkboard(rng,0)
        self.assertEqual(empty,[0]*16)
        rng,filled=mkboard(rng,1)
        self.assertEqual(filled,[2]*16)
        rng,wins=mkboard(rng,2)
        self.assertEqual(wins,[2048]*16)

    def test_xorshift_reproducible(self):
        self.assertEqual(next_rand(0x31415926),next_rand(0x31415926))
        self.assertNotEqual(next_rand(0x31415926),0x31415926)

    def test_fnv_input_affects_hash(self):
        self.assertNotEqual(put32(0xcbf29ce484222325,1),
                            put32(0xcbf29ce484222325,2))


@unittest.skipUnless(AVAILABLE,'real ARM64 v2 bundle required; set EDGEAI_QEMU_V2_BUNDLE')
class RealArm64MachineTests(unittest.TestCase):
    def test_22000_machine_calls_equal_generated_cpp(self):
        report=verify(CASES,ELF,MANIFEST,LIB)
        self.assertTrue(report['passed'])
        self.assertEqual(report['cases_compared'],22000)
        self.assertEqual(report['function_count'],11)

    def test_negative_control_first_wrong_board_winner_case(self):
        report=verify(CASES,ELF,MANIFEST,MUTANT)
        self.assertFalse(report['passed'])
        self.assertEqual(report['functions_with_mismatches'],1)
        item=next(x for x in report['results'] if x['first_mismatch'])
        self.assertEqual(item['address'],'0x400dc4')
        self.assertEqual(item['first_mismatch']['case'],2)
        self.assertEqual(item['first_mismatch']['candidate_state']['board_input'],[2048]*16)

    def test_corrupted_order_fails(self):
        config=json.loads(MANIFEST.read_text())
        with tempfile.TemporaryDirectory() as td:
            tampered=Path(td)/'machine.txt'
            tampered.write_text(CASES.read_text().replace(
                'ARM64_CASE slot=0 case=1','ARM64_CASE slot=0 case=3',1))
            with self.assertRaises(ValueError):
                check_cases(tampered,config,2000)

    def test_modified_elf_fails_sha(self):
        with tempfile.TemporaryDirectory() as td:
            modified=Path(td)/'wrong.elf'
            b=bytearray(ELF.read_bytes());b[-100]^=1;modified.write_bytes(b)
            with self.assertRaisesRegex(ValueError,'SHA'):
                verify(CASES,modified,MANIFEST,LIB)


if __name__=='__main__':unittest.main()
