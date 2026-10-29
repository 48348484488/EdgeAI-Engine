"""Independent negative controls: the V15 score manifest must be byte-pinned."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v15_parity', ROOT/'tools/verify_2048_v15_qemu_parity.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ManifestIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.original = (ROOT/'benchmarks/2048_v15/score_cases.tsv').read_bytes()

    def assert_rejected(self, altered):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'cases.tsv'
            path.write_bytes(altered)
            with self.assertRaisesRegex(ValueError, 'unpinned V15 case manifest'):
                module.parse_cases(path)

    def test_pinned_original(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'cases.tsv'
            path.write_bytes(self.original)
            cases = module.parse_cases(path)
            self.assertEqual((len(cases), sum(map(lambda c:len(c[0]), cases)),
                              sum(c[1] for c in cases)), (20,179,11914))

    def test_modified_score_rejected(self):
        self.assert_rejected(self.original.replace(b'0\t59\t', b'9\t59\t', 1))

    def test_modified_expected_hash_rejected(self):
        self.assert_rejected(self.original.replace(b'ce3ae4bd', b'ae3ae4bd', 1))

    def test_reordered_cases_rejected(self):
        rows = self.original.splitlines(keepends=True)
        rows[2], rows[3] = rows[3], rows[2]
        self.assert_rejected(b''.join(rows))

    def test_trailing_newline_required(self):
        self.assert_rejected(self.original.rstrip(b'\n'))

    def test_extra_payload_rejected(self):
        self.assert_rejected(self.original + b'# additional payload\n')

    def test_oversized_rejected(self):
        self.assert_rejected(self.original + b' ' * 4097)

if __name__ == '__main__':
    unittest.main()
