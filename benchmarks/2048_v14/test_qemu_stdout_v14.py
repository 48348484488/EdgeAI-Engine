"""Integrity gates for reference stdout captured by actual ARM64 ELF under QEMU.

Set EDGEAI_V14_BUNDLE to an extracted V14 archive (must include original
QEMU output, original ELF and regenerated C++ library).
"""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT=Path(os.environ.get("EDGEAI_V14_BUNDLE","/missing-v14-bundle"))
sys.path.insert(0,str(ROOT/"tools"))
AVAILABLE=(ROOT/"qemu_real/original_artifact/original_stdout_manifest.json").is_file()

@unittest.skipUnless(AVAILABLE,"requires actual original QEMU stdout from the V14 bundle")
class RealArm64OutputOracle(unittest.TestCase):
    def setUp(self):
        from compare_2048_v14_qemu_stdout import compare
        self.compare=compare
        self.original=ROOT/"qemu_real/original_artifact"

    def test_true_original_machine_output_matches_compiled_cpp(self):
        with tempfile.TemporaryDirectory() as t:
            outcome=self.compare(self.original,Path(t)/"result.json")
            self.assertEqual((outcome["cases_compared"],outcome["bytes_equal"],outcome["mismatches"]),(21,21880,0))

    def test_corrupted_machine_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            where=Path(t)/"data"
            shutil.copytree(self.original,where)
            p=where/"original_case_02.bin"
            damaged=bytearray(p.read_bytes());damaged[0]^=1;p.write_bytes(damaged)
            with self.assertRaisesRegex(ValueError,"tampered"):
                self.compare(where,Path(t)/"result.json")

    def test_machine_case_provenance_is_checked(self):
        import json
        with tempfile.TemporaryDirectory() as t:
            where=Path(t)/"data"
            shutil.copytree(self.original,where)
            p=where/"original_stdout_manifest.json"
            d=json.loads(p.read_text())
            d["cases"][0]["input"]["value"]=42
            p.write_text(json.dumps(d))
            with self.assertRaisesRegex(ValueError,"provenance"):
                self.compare(where,Path(t)/"result.json")

    def test_missing_machine_output_never_counts_as_success(self):
        with tempfile.TemporaryDirectory() as t:
            where=Path(t)/"data"
            shutil.copytree(self.original,where)
            (where/"original_case_20.bin").unlink()
            with self.assertRaises(FileNotFoundError):
                self.compare(where,Path(t)/"result.json")

if __name__=="__main__":
    unittest.main()
