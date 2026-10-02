import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
import v012_fresh_holdout as h

class V012FreshHoldoutTests(unittest.TestCase):
    def test_fresh_holdout_is_128_unique_nonoverlapping_rows(self):
        rows=h.fresh_rows()
        self.assertEqual(len(rows),128)
        self.assertEqual(len({r['id'] for r in rows}),128)
        self.assertTrue(h.validate_fresh(rows,ROOT/'data/instructions_v07'))
        self.assertEqual({r['task'] for r in rows},{'copy','uppercase','addition','expression'})

if __name__=='__main__':unittest.main()
