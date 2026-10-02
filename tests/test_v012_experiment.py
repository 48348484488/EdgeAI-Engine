import sys
import unittest
from pathlib import Path

import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))

import instruction_blocks_v012 as exp
sys.path.insert(0,str(ROOT/'tools'))
from transformer_model import TinyTransformer


class V012ExperimentContractTests(unittest.TestCase):
    def test_defaults_pin_fair_cpu_protocol(self):
        self.assertEqual(exp.SEEDS,(11,22,33))
        self.assertEqual(exp.ARCHITECTURES,(1,2))
        self.assertEqual(exp.DEFAULT_THREADS,1)
        self.assertEqual(exp.DEFAULT_CPU_SECONDS,60.0)

    def test_fair_pair_allows_only_block_count_to_differ(self):
        base=dict(
            protocol='edge-sft-v012-blocks-1',
            seed=11,cpu_budget=60.0,threads=1,
            dataset_sha256='dataset',tokenizer_fingerprint='tokenizer',
            dim=64,hidden=96,window=64,precision='int8',
            batch=16,lr=.001,weight_decay=.01,clip_norm=1.0,
            max_length=128,
            selection='minimum response validation NLL at 25/50/75/100 percent',
        )
        one=dict(base,blocks=1)
        two=dict(base,blocks=2)
        exp.assert_fair_pair(one,two)

    def test_fair_pair_rejects_hidden_hyperparameter_change(self):
        base=dict(
            protocol='edge-sft-v012-blocks-1',
            seed=22,cpu_budget=60.0,threads=1,
            dataset_sha256='dataset',tokenizer_fingerprint='tokenizer',
            dim=64,hidden=96,window=64,precision='int8',
            batch=16,lr=.001,weight_decay=.01,clip_norm=1.0,
            max_length=128,
            selection='minimum response validation NLL at 25/50/75/100 percent',
        )
        one=dict(base,blocks=1)
        two=dict(base,blocks=2,lr=.002)
        with self.assertRaises(ValueError):
            exp.assert_fair_pair(one,two)


    def test_promote_to_two_blocks_preserves_base_and_is_deterministic(self):
        torch.manual_seed(123)
        base=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',blocks=1)
        base.eval()
        before={k:v.detach().clone() for k,v in base.state_dict().items()}

        two_a=exp.promote_blocks(base,2,seed=77)
        two_b=exp.promote_blocks(base,2,seed=77)
        two_c=exp.promote_blocks(base,2,seed=78)

        self.assertEqual(len(two_a.blocks),2)
        torch.testing.assert_close(two_a.emb.weight,base.emb.weight,rtol=0,atol=0)
        torch.testing.assert_close(two_a.out.weight,base.out.weight,rtol=0,atol=0)
        torch.testing.assert_close(two_a.out.bias,base.out.bias,rtol=0,atol=0)
        for name,value in base.blocks[0].state_dict().items():
            torch.testing.assert_close(two_a.blocks[0].state_dict()[name],value,rtol=0,atol=0)
        for name,value in two_a.blocks[1].state_dict().items():
            torch.testing.assert_close(two_b.blocks[1].state_dict()[name],value,rtol=0,atol=0)
        self.assertTrue(any(
            not torch.equal(two_a.blocks[1].state_dict()[name],two_c.blocks[1].state_dict()[name])
            for name in two_a.blocks[1].state_dict()
        ))
        for key,value in before.items():
            torch.testing.assert_close(base.state_dict()[key],value,rtol=0,atol=0)

    def test_promote_one_block_returns_independent_copy(self):
        torch.manual_seed(456)
        base=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',blocks=1)
        one=exp.promote_blocks(base,1,seed=99)
        self.assertIsNot(one,base)
        self.assertEqual(one.export_config(),base.export_config())
        for key,value in base.state_dict().items():
            torch.testing.assert_close(one.state_dict()[key],value,rtol=0,atol=0)


if __name__=='__main__':
    unittest.main()
