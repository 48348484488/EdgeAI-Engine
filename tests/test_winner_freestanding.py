"""Real Clang/LLD ARM32 compile checks, without pretending to run QEMU."""
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from validate_winner_freestanding import validate, verify_static_arm_elf

class FreestandingTests(unittest.TestCase):
    def test_five_arm32_static_binary_links(self):
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/'binaries'
            report=validate(Path(td)/'report.json',qemu=None,save_runners=output)
            self.assertEqual(report['compiled_runners'],5)
            self.assertEqual(report['execution_status'],'not_executed_missing_qemu')
            self.assertEqual(report['qemu_tested_cases'],0)
            for entry in report['runs']:
                saved=output/('winner_arm32_'+entry['optimization'].replace('-','')+'.elf')
                self.assertTrue(saved.is_file())
                self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(),entry['elf']['sha256'])
            self.assertTrue(all(entry['elf']['machine']=='ARM' and
                                not entry['elf']['dynamic_interpreter'] and
                                entry['elf']['type']=='ET_EXEC' for entry in report['runs']))
            self.assertTrue(all(entry['behavior'] is None for entry in report['runs']))
    def test_qemu_required_fails_closed_and_saves_report(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'report.json'
            with self.assertRaisesRegex(RuntimeError,'QEMU ARM test not passed'):
                validate(path,qemu=None,require_qemu=True,optimizations=('1',))
            saved=json.loads(path.read_text())
            self.assertEqual(saved['execution_status'],'not_executed_missing_qemu')
            self.assertEqual(saved['qemu_tested_cases'],0)
    def test_host_non_elf_rejected(self):
        with self.assertRaisesRegex(ValueError,'not little-endian ELF32'):
            verify_static_arm_elf(__file__)

if __name__=='__main__':unittest.main()
