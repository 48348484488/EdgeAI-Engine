import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))

import instruction_blocks_v012 as exp


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


if __name__=='__main__':
    unittest.main()
