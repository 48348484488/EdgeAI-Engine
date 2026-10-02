import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
import v013_length_stabilized as train
import evaluate_v013_length_stabilized as ev

class StabilizedLengthV013Tests(unittest.TestCase):
    def test_protocol_is_pinned(self):
        self.assertEqual(train.SEEDS,(11,22,33))
        self.assertEqual(train.CPU_SECONDS,60.0)
        self.assertEqual(train.THREADS,1)
        self.assertEqual(train.INIT_MODE,'copy_inner_identity')
        self.assertEqual(train.INNER_LR_SCALE,.25)

    def test_candidate_report_requires_three_two_block_seeds(self):
        good=dict(expected=3,completed=3,runs=[dict(seed=s,blocks=2) for s in (11,22,33)])
        self.assertTrue(ev.validate_candidate(good))
        bad=dict(good);bad['runs']=good['runs'][:2]
        self.assertFalse(ev.validate_candidate(bad))

if __name__=='__main__':unittest.main()
