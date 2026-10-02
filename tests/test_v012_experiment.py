import sys
import unittest
from pathlib import Path

import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))

import instruction_blocks_v012 as exp
import instruction_blocks_eval_v012 as eval12
import analyze_v012_depth as depth12
import instruction_blocks_equal_steps_v012 as equal12
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

    def test_promote_two_blocks_starts_as_same_function(self):
        torch.manual_seed(321)
        base=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',blocks=1)
        base.eval()
        tokens=torch.tensor([[1,2,3,4,5,6]],dtype=torch.long)
        before=base(tokens).detach().clone()
        two=exp.promote_blocks(base,2,seed=77).eval()
        torch.testing.assert_close(base(tokens),before,rtol=0,atol=0,msg='promotion mutated base model')
        base_h=base._forward_block(base.emb(tokens),base.blocks[0])
        two_h=two._forward_block(two.emb(tokens),two.blocks[0])
        torch.testing.assert_close(two_h,base_h,rtol=0,atol=0,msg='copied first block diverged')
        two_h2=two._forward_block(two_h,two.blocks[1])
        torch.testing.assert_close(two_h2,two_h,rtol=0,atol=0,msg='second block is not identity')
        torch.testing.assert_close(two(tokens),before,rtol=0,atol=0,msg='final promoted function diverged')

    def test_promote_one_block_returns_independent_copy(self):
        torch.manual_seed(456)
        base=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',blocks=1)
        one=exp.promote_blocks(base,1,seed=99)
        self.assertIsNot(one,base)
        self.assertEqual(one.export_config(),base.export_config())
        for key,value in base.state_dict().items():
            torch.testing.assert_close(one.state_dict()[key],value,rtol=0,atol=0)


    def test_build_identity_differs_only_by_blocks(self):
        config=dict(dim=64,hidden=96,window=64,precision='int8',vocab_size=515,blocks=1)
        one=exp.build_identity(
            seed=33,blocks=1,cpu_budget=60.0,threads=1,
            dataset_sha256='dataset',tokenizer_fingerprint='tokenizer',config=config)
        two=exp.build_identity(
            seed=33,blocks=2,cpu_budget=60.0,threads=1,
            dataset_sha256='dataset',tokenizer_fingerprint='tokenizer',config=config)
        exp.assert_fair_pair(one,two)
        changed={k for k in set(one)|set(two) if one.get(k)!=two.get(k)}
        self.assertEqual(changed,{'blocks'})

    def test_build_identity_versions_identity_initialized_protocol(self):
        config=dict(dim=64,hidden=96,window=64,precision='int8',vocab_size=515,blocks=2)
        row=exp.build_identity(
            seed=11,blocks=2,cpu_budget=60.0,threads=1,
            dataset_sha256='d',tokenizer_fingerprint='t',config=config)
        self.assertEqual(row['protocol'],'edge-sft-v012-blocks-identity-v2')

    def test_build_identity_pins_v07_sft_hyperparameters(self):
        config=dict(dim=64,hidden=96,window=64,precision='int8',vocab_size=515,blocks=1)
        row=exp.build_identity(
            seed=11,blocks=1,cpu_budget=60.0,threads=1,
            dataset_sha256='d',tokenizer_fingerprint='t',config=config)
        self.assertEqual(row['batch'],16)
        self.assertEqual(row['lr'],.001)
        self.assertEqual(row['weight_decay'],.01)
        self.assertEqual(row['clip_norm'],1.0)
        self.assertEqual(row['max_length'],128)
        self.assertEqual(row['selection'],'minimum response validation NLL at 25/50/75/100 percent')



    def test_repo_output_dir_resolves_relative_path_inside_repository(self):
        resolved=exp.repo_output_dir(Path('models/v012'))
        self.assertTrue(resolved.is_absolute())
        self.assertEqual(resolved,ROOT/'models/v012')

    def test_repo_output_dir_rejects_path_outside_repository(self):
        with self.assertRaises(ValueError):
            exp.repo_output_dir(Path('/tmp/edgeai-v012-out'))


    def test_eval_summary_counts_exact_correct_and_eos(self):
        rows=[
            dict(exact=True,correct=True,stopped_on_eos=True,generated_tokens=2,total_seconds=.01),
            dict(exact=False,correct=True,stopped_on_eos=False,generated_tokens=4,total_seconds=.03),
        ]
        summary=eval12.summarize(rows)
        self.assertEqual(summary['count'],2)
        self.assertEqual(summary['exact'],1)
        self.assertEqual(summary['correct'],2)
        self.assertEqual(summary['eos'],1)
        self.assertEqual(summary['correct_and_eos'],1)
        self.assertEqual(summary['median_generated_tokens'],3.0)

    def test_eval_rejects_incomplete_training_report(self):
        with self.assertRaises(ValueError):
            eval12.validate_training_report(dict(expected=6,completed=5,runs=[]))


    def test_repo_path_resolves_relative_cli_paths_under_repository(self):
        resolved=exp.repo_path(Path('models/v012'))
        self.assertTrue(resolved.is_absolute())
        self.assertEqual(resolved,ROOT/'models/v012')

    def test_repo_path_preserves_absolute_repository_path(self):
        expected=ROOT/'results/v012/training.json'
        self.assertEqual(exp.repo_path(expected),expected)


    def test_depth_diagnosis_exposes_compute_and_generation_tradeoff(self):
        training=dict(runs=[
            dict(seed=11,blocks=1,steps=100,selected_validation_nll=.5),
            dict(seed=11,blocks=2,steps=65,selected_validation_nll=.4),
        ])
        evaluation=dict(runs=[
            dict(seed=11,blocks=1,summary=dict(count=10,correct=6,median_internal_seconds=.001)),
            dict(seed=11,blocks=2,summary=dict(count=10,correct=5,median_internal_seconds=.0012)),
        ])
        d=depth12.diagnose(training,evaluation)
        self.assertEqual(d['one_correct'],6)
        self.assertEqual(d['two_correct'],5)
        self.assertEqual(d['correct_delta'],-1)
        self.assertEqual(d['validation_prefers_two'],1)
        self.assertEqual(d['generation_prefers_two'],0)
        self.assertAlmostEqual(d['median_two_step_ratio'],.65)
        self.assertAlmostEqual(d['median_latency_ratio'],1.2)


    def test_equal_step_ablation_uses_frozen_one_block_counts(self):
        self.assertEqual(equal12.target_steps(11),11269)
        self.assertEqual(equal12.target_steps(22),11286)
        self.assertEqual(equal12.target_steps(33),9661)
        with self.assertRaises(ValueError):
            equal12.target_steps(44)


if __name__=='__main__':
    unittest.main()
