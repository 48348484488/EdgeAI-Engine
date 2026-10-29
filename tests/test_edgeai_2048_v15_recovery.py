"""Regression tests for fail-closed V15 2048 provider recovery."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from edgeai_2048_v15_recovery import rebuild

GENERATOR = '''import argparse, hashlib, json, subprocess
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('elf'); p.add_argument('--output-dir'); p.add_argument('--enable-stateful-printf', action='store_true'); a=p.parse_args()
o=Path(a.output_dir)
(o/'candidate_2000.cpp').write_text('extern "C" int recovered_2000(){return 7;}')
(o/'candidate_3000.cpp').write_text('extern "C" int recovered_2000(); extern "C" int recovered_3000(){return recovered_2000();}')
subprocess.run(['g++','-shared','-fPIC','-Wl,-z,defs',str(o/'candidate_2000.cpp'),str(o/'candidate_3000.cpp'),'-o',str(o/'recovered_candidates.so')],check=True)
r={'binary_sha256':hashlib.sha256(Path(a.elf).read_bytes()).hexdigest(),'source_read':False,'symbols_used':False,'compile_status':'SUCCEEDED','cpp_emitted_candidate_count':2,'functions':[{'address':'0x2000','status':'CPP_EMITTED_NOT_BEHAVIORALLY_VALIDATED'},{'address':'0x3000','status':'CPP_EMITTED_NOT_BEHAVIORALLY_VALIDATED'}]}
(o/'coverage.json').write_text(json.dumps(r))
'''


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.elf = self.root / 'original.elf'
        self.elf.write_bytes(b'fixture ELF')
        self.hash = hashlib.sha256(self.elf.read_bytes()).hexdigest()
        self.tool = self.root / 'tools'
        self.tool.mkdir()
        (self.tool / 'aarch64_multistage_batch.py').write_text(GENERATOR)
        original = Path(__file__).resolve().parents[1] / 'tools' / 'edgeai_cpp_link_gate.py'
        (self.tool / 'edgeai_cpp_link_gate.py').write_bytes(original.read_bytes())
        self.out = self.root / 'bundle'

    def go(self, **kw):
        return rebuild(self.elf, self.out, self.tool, expected_count=2,
                       expected_elf_sha256=self.hash, **kw)

    def test_success_publishes_real_linked_sources(self):
        result = self.go()
        self.assertEqual(result['generated_candidates'], 2)
        self.assertTrue((self.out / 'bundle_manifest.json').exists())
        self.assertTrue(json.loads((self.out / 'native_link.json').read_text())['passed'])
        self.assertFalse(result['arm64_qemu_parity_tested_in_this_run'])

    def test_rejects_wrong_elf_before_running(self):
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            rebuild(self.elf, self.out, self.tool, expected_count=2)
        self.assertFalse(self.out.exists())

    def test_rejects_missing_export_without_partial_bundle(self):
        script = self.tool / 'aarch64_multistage_batch.py'
        script.write_text(script.read_text().replace('recovered_3000(){', 'wrong_export(){'))
        with self.assertRaises(RuntimeError):
            self.go()
        self.assertFalse(self.out.exists())

    def test_rejects_count_mismatch_without_partial_bundle(self):
        with self.assertRaisesRegex(RuntimeError, 'candidate count'):
            rebuild(self.elf, self.out, self.tool, expected_count=3,
                    expected_elf_sha256=self.hash)
        self.assertFalse(self.out.exists())

    def test_existing_bundle_never_overwritten(self):
        self.out.mkdir()
        sentinel = self.out / 'sentinel.txt'
        sentinel.write_text('keep')
        with self.assertRaises(FileExistsError):
            self.go()
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_rejects_provenance_forgery(self):
        script = self.tool / 'aarch64_multistage_batch.py'
        script.write_text(script.read_text().replace("'source_read':False", "'source_read':True"))
        with self.assertRaisesRegex(RuntimeError, 'source-blind'):
            self.go()
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
