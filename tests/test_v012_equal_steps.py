import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
import instruction_blocks_equal_steps_v012 as eq

class EqualStepsV012Tests(unittest.TestCase):
    def test_protocol_constants_are_pinned(self):
        self.assertEqual(eq.SEEDS,(11,22,33))
        self.assertEqual(eq.ARCHITECTURES,(1,2))
        self.assertEqual(eq.DEFAULT_THREADS,1)

    def test_pair_identity_differs_only_by_blocks(self):
        config=dict(dim=48,hidden=128,window=64,precision='int8',vocab_size=515)
        one=eq.build_identity(11,1,11269,1,'dataset','tok',config)
        two=eq.build_identity(11,2,11269,1,'dataset','tok',config)
        eq.assert_fair_pair(one,two)
        changed={k for k in set(one)|set(two) if one.get(k)!=two.get(k)}
        self.assertEqual(changed,{'blocks'})

    def test_pair_rejects_different_step_budget(self):
        config=dict(dim=48,hidden=128,window=64,precision='int8',vocab_size=515)
        one=eq.build_identity(22,1,11286,1,'dataset','tok',config)
        two=eq.build_identity(22,2,8000,1,'dataset','tok',config)
        with self.assertRaises(ValueError):
            eq.assert_fair_pair(one,two)

    def test_baseline_plan_freezes_one_block_schedule(self):
        report=dict(fairness_verified=True,runs=[
            dict(seed=11,blocks=1,steps=100,selected_step=50,selected_validation_nll=.4,
                 validation_curve=[dict(step=25),dict(step=50),dict(step=75),dict(step=100)],
                 batch_ids_sha256='abc',examples_seen={'copy':1600},source_checkpoint_sha256='def')
        ])
        p=eq.baseline_plan(report,11)
        self.assertEqual(p['target_steps'],100)
        self.assertEqual(p['validation_steps'],[25,50,75,100])
        self.assertEqual(p['batch_ids_sha256'],'abc')

    def test_baseline_plan_rejects_unverified_source(self):
        with self.assertRaises(ValueError):
            eq.baseline_plan(dict(fairness_verified=False,runs=[]),11)

if __name__=='__main__':
    unittest.main()
