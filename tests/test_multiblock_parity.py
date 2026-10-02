import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))

from verify_multiblock import verify


class MultiBlockNativeParity(unittest.TestCase):
    def test_python_native_parity_for_one_and_two_blocks_with_cache_wrap(self):
        build=ROOT/'build'
        self.assertTrue((build/'edgeai_token_logits').is_file())
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'parity.json'
            report=verify(build,out)
            self.assertTrue(report['all_passed'])
            self.assertEqual({row['blocks'] for row in report['cases']},{1,2})
            self.assertTrue(all(row['tokens']>row['window'] for row in report['cases']))
            self.assertLessEqual(report['max_abs_error'],6e-5)
            self.assertEqual(json.loads(out.read_text())['all_passed'],True)


if __name__=='__main__':
    unittest.main()
