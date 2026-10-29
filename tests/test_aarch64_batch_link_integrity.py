"""Fail-closed compiler and repeat-run regression tests for ARM64 C++ batch."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from aarch64_multistage_batch import _compile_candidates, run


class BatchLinkIntegrityTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'), 'g++ required')
    def test_valid_cpp_is_linked(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out/'candidate_1.cpp').write_text('extern "C" int recovered(){return 42;}\n')
            status, error = _compile_candidates(out, [{'file':'candidate_1.cpp'}])
            self.assertEqual((status,error), ('SUCCEEDED',None))
            self.assertTrue((out/'recovered_candidates.so').is_file())
            self.assertFalse((out/'recovered_candidates.so.tmp').exists())

    @unittest.skipUnless(shutil.which('g++'), 'g++ required')
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
        # Synthetic scan: this test does not depend on large ELF test artifacts.
        empty_scan = {
            'symbols_used': False, 'source_read': False,
            'input_sha256': '0'*64, 'candidate_entries': [],
            'text_address': '0x1000', 'text_size_bytes': 0,
        }
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out/'candidate_deadbeef.cpp').write_text('stale')
            (out/'recovered_candidates.so').write_bytes(b'PREVIOUS_SUCCESS')
            with patch('aarch64_multistage_batch.analyze', return_value=empty_scan):
                with patch('aarch64_multistage_batch.generate_stack_pair',
                           side_effect=ValueError('no pair')):
                    report = run(Path('unused.elf'), out, compile_cpp=False)
            self.assertEqual(report['cpp_emitted_candidate_count'], 0)
            self.assertEqual(report['compile_status'], 'NOT_REQUESTED')
            self.assertFalse((out/'candidate_deadbeef.cpp').exists())
            self.assertFalse((out/'recovered_candidates.so').exists())
            self.assertEqual(len(list(out.glob('candidate_*.cpp'))), 0)


if __name__=='__main__':
    unittest.main()
