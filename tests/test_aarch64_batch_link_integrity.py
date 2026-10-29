"""Fail-closed compiler and repeat-run regression tests for ARM64 C++ batch."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from aarch64_multistage_batch import _compile_candidates, run

ROOT = Path(__file__).resolve().parents[1]
ELF = ROOT/'bin/2048-arm64-stripped.elf'
ELF_SHA256 = 'a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b'


class BatchLinkIntegrityTests(unittest.TestCase):
    def test_valid_cpp_is_linked(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out/'candidate_1.cpp').write_text('extern "C" int recovered(){return 42;}\n')
            status, error = _compile_candidates(out, [{'file':'candidate_1.cpp'}])
            self.assertEqual((status,error), ('SUCCEEDED',None))
            self.assertTrue((out/'recovered_candidates.so').is_file())
            self.assertFalse((out/'recovered_candidates.so.tmp').exists())

    def test_undefined_external_symbol_rejected_and_old_library_removed(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out/'recovered_candidates.so').write_bytes(b'PREVIOUS_SUCCESS')
            (out/'candidate_1.cpp').write_text(
                'extern "C" int missing();\nextern "C" int recovered(){return missing();}\n')
            status, error = _compile_candidates(out, [{'file':'candidate_1.cpp'}])
            self.assertEqual(status,'FAILED')
            self.assertIn('missing',error)
            self.assertFalse((out/'recovered_candidates.so').exists())
            self.assertFalse((out/'recovered_candidates.so.tmp').exists())

    def test_repeat_run_cleans_stale_candidates_and_library(self):
        self.assertEqual(hashlib.sha256(ELF.read_bytes()).hexdigest(), ELF_SHA256)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out/'candidate_deadbeef.cpp').write_text('stale')
            (out/'recovered_candidates.so').write_bytes(b'PREVIOUS_SUCCESS')
            report = run(ELF, out, compile_cpp=False)
            self.assertEqual(report['cpp_emitted_candidate_count'], 18)
            self.assertEqual(report['compile_status'], 'NOT_REQUESTED')
            self.assertFalse((out/'candidate_deadbeef.cpp').exists())
            self.assertFalse((out/'recovered_candidates.so').exists())
            self.assertEqual(len(list(out.glob('candidate_*.cpp'))),18)


if __name__=='__main__':
    unittest.main()
