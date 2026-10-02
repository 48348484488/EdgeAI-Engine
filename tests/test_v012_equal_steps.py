import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
import instruction_blocks_equal_steps_v012 as eq

class EqualStepsV012Tests(unittest.TestCase):
    def test_defaults_pin_equal_step_protocol(self):
        self.assertEqual(eq.SEEDS,(11,22,33))
        self.assertEqual(eq.ARCHITECTURES,(1,2))
        self.assertEqual(eq.DEFAULT_THREADS,1)
        self.assertEqual(eq.DEFAULT_STEPS,9000)

    def test_pair_identity_differs_only_by_blocks(self):
        config=dict(dim=48,hidden=128,window=64,precision='int8',vocab_size=515)
        one=eq.build_identity(11,1,9000,1,'dataset','tok',config)
        two=eq.build_identity(11,2,9000,1,'dataset','tok',config)
        eq.assert_fair_pair(one,two)
        changed={k for k in set(one)|set(two) if one.get(k)!=two.get(k)}
        self.assertEqual(changed,{'blocks'})

    def test_pair_rejects_different_step_budget(self):
        config=dict(dim=48,hidden=128,window=64,precision='int8',vocab_size=515)
        one=eq.build_identity(22,1,9000,1,'dataset','tok',config)
        two=eq.build_identity(22,2,8000,1,'dataset','tok',config)
        with self.assertRaises(ValueError):
            eq.assert_fair_pair(one,two)

if __name__=='__main__':
    unittest.main()
