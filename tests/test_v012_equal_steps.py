import sys
import unittest
import torch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
import instruction_blocks_equal_steps_v012 as eq
sys.path.insert(0,str(ROOT/'tools'))
from transformer_model import TinyTransformer

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
                 batch_ids_sha256='abc',examples_seen={'copy':1600},source_checkpoint_sha256='def',
                 train_cpu_seconds=1.0,train_wall_seconds=1.1)
        ])
        p=eq.baseline_plan(report,11)
        self.assertEqual(p['target_steps'],100)
        self.assertEqual(p['validation_steps'],[25,50,75,100])
        self.assertEqual(p['batch_ids_sha256'],'abc')

    def test_baseline_plan_rejects_unverified_source(self):
        with self.assertRaises(ValueError):
            eq.baseline_plan(dict(fairness_verified=False,runs=[]),11)


    def test_copy_inner_identity_preserves_function_and_copies_features(self):
        torch.manual_seed(123)
        base=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',vocab_size=256,blocks=1).eval()
        tokens=torch.tensor([[1,2,3,4]],dtype=torch.long)
        before=base(tokens).detach().clone()
        two=eq.promote_for_init(base,77,'copy_inner_identity').eval()
        torch.testing.assert_close(two(tokens),before,rtol=0,atol=0)
        for name in ('query','key','value','up'):
            for key,value in getattr(base.blocks[0],name).state_dict().items():
                torch.testing.assert_close(getattr(two.blocks[1],name).state_dict()[key],value,rtol=0,atol=0)
        self.assertEqual(float(two.blocks[1].project.weight.abs().sum()),0.0)
        self.assertEqual(float(two.blocks[1].down.weight.abs().sum()),0.0)

    def test_unknown_init_mode_is_rejected(self):
        base=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',vocab_size=256,blocks=1)
        with self.assertRaises(ValueError):
            eq.promote_for_init(base,11,'nope')


    def test_new_block_inner_lr_can_be_scaled(self):
        base=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',vocab_size=256,blocks=1)
        two=eq.promote_for_init(base,77,'copy_inner_identity')
        opt=eq.make_optimizer(two,.25)
        lrs=sorted({group['lr'] for group in opt.param_groups})
        self.assertEqual(lrs,[.00025,.001])

    def test_new_block_inner_lr_scale_rejects_zero(self):
        base=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',vocab_size=256,blocks=1)
        two=eq.promote_for_init(base,77,'copy_inner_identity')
        with self.assertRaises(ValueError):
            eq.make_optimizer(two,0)

if __name__=='__main__':
    unittest.main()
