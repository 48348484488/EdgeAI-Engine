"""Offline fail-closed tests for pinned 2048 V15 ARM64 parity manifest."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v15_parity', ROOT/'tools/verify_2048_v15_qemu_parity.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class V15ManifestTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT/'benchmarks/2048_v15/score_cases.tsv'

    def test_pinned_cases(self):
        cases = module.parse_cases(self.path)
        self.assertEqual(len(cases), 20)
        self.assertEqual(sum(len(c[0]) for c in cases), 179)
        self.assertEqual(sum(c[1] for c in cases), 11914)

    def test_missing_proof_rejected(self):
        with self.assertRaisesRegex(ValueError, 'provide'):
            module.verify(self.path)

    def test_bad_header_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'bad.tsv'
            p.write_text(self.path.read_text().replace('Generated C++', 'handwritten C++'))
            with self.assertRaisesRegex(ValueError, 'unpinned'):
                module.parse_cases(p)

    def test_bad_output_detected(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(20):
                (Path(d)/f'original_case_{i:02d}.bin').write_bytes(b'not original')
            with self.assertRaisesRegex(AssertionError, 'mismatch'):
                module.verify(self.path, original_dir=d)


if __name__ == '__main__':
    unittest.main()
