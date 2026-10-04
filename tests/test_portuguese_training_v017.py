"""Training contracts: leakage, response boundaries, budgets and replay safety."""
import importlib
import hashlib
import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

try:
    training = importlib.import_module('benchmarks.portuguese_v017')
except ModuleNotFoundError as error:
    if error.name != 'benchmarks.portuguese_v017':
        raise
    training = None


class TrainingContracts(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(training, 'Portuguese training pipeline is missing')

    def test_mask_excludes_prompt_response_marker_and_padding_but_keeps_eos(self):
        tok = training.ByteBPE((), instruction=True)
        x, y = training.encode_row(dict(prompt='Oi', response='OK'), tok, 16)
        self.assertEqual(x, [256, 79, 105, 257, 79, 75])
        self.assertEqual(y, [-100, -100, -100, 79, 75, 258])
        with self.assertRaisesRegex(ValueError, 'max_length'):
            training.encode_row(dict(prompt='Oi', response='OK'), tok, 5)

    def test_tokenizer_cannot_learn_held_out_documents(self):
        data = training.load_training_data(training.SOURCE_ROOT)
        tok = training.train_tokenizer(data['train'], 291)
        expected = training.ByteBPE.train(
            [row[field].encode('utf-8') for row in data['train']
             for field in ('prompt', 'response')], vocab_size=289)
        self.assertEqual(tok.merges, expected.merges)
        self.assertTrue(tok.instruction)
        self.assertLessEqual(tok.vocab_size, 291)
        self.assertEqual(set(data), {'train', 'valid', 'hashes'})
        contaminated = data['train'] + data['valid']
        with self.assertRaisesRegex(ValueError, 'train'):
            training.train_tokenizer(contaminated, 291)
        import json
        held_out = json.loads((training.SOURCE_ROOT / 'test.jsonl').read_text(
            encoding='utf-8').splitlines()[0])
        with self.assertRaisesRegex(ValueError, 'train'):
            training.train_tokenizer(data['train'] + [held_out], 291)

    def test_training_loader_and_tokenizer_never_open_test_jsonl(self):
        original_open = Path.open

        def reject_test_split(path, *args, **kwargs):
            if path.name == 'test.jsonl':
                raise AssertionError('trainer opened sealed test.jsonl')
            return original_open(path, *args, **kwargs)

        with patch.object(Path, 'open', reject_test_split):
            data = training.load_training_data(training.SOURCE_ROOT)
            training.train_tokenizer(data['train'], 291)

    def test_batch_stream_replays_identically_and_shuffles_each_epoch(self):
        order = training.batch_order(5, 11, 12)
        self.assertEqual(order, training.batch_order(5, 11, 12))
        self.assertNotEqual(order, training.batch_order(5, 22, 12))
        self.assertEqual(set(order[:5]), set(range(5)))
        self.assertEqual(set(order[5:10]), set(range(5)))

    def test_each_seed_consumes_the_exact_same_budget(self):
        config = training.TrainConfig.for_profile('release')
        budgets = []
        rows = [dict(id=str(i), x=[1] * (i + 2), y=[-100] + [2] * (i + 1))
                for i in range(4)]
        for seed in config.seeds:
            schedule = training.training_schedule(rows, replace(config, steps=3,
                                                    response_tokens_per_step=7), seed)
            budgets.append(sum(sum(y != -100 for y in part['y'])
                               for step in schedule for part in step))
        self.assertEqual(budgets, [21, 21, 21])
        self.assertEqual(config.seeds, (11, 22, 33))
        self.assertLessEqual(config.threads, 2)

    def test_selection_uses_only_validation_and_rejects_test_metrics(self):
        curve = [dict(step=1, split='valid', response_nll=2.),
                 dict(step=2, split='valid', response_nll=1.),
                 dict(step=3, split='valid', response_nll=1.)]
        self.assertEqual(training.select_checkpoint(curve)['step'], 2)
        with self.assertRaisesRegex(ValueError, 'valid'):
            training.select_checkpoint(curve + [dict(step=4, split='test', response_nll=0.)])
        with self.assertRaisesRegex(ValueError, 'finite'):
            training.select_checkpoint([dict(step=1, split='valid', response_nll=float('nan'))])

    def test_resume_rejects_changed_seed_tokenizer_data_budget_and_optimizer(self):
        config = training.TrainConfig()
        identity = training.resume_identity(config, 11, {'train': 'a', 'valid': 'b'}, 'tok')
        training.validate_resume(identity, identity)
        for field in ('seed', 'tokenizer_sha256', 'data', 'config'):
            bad = dict(identity)
            bad[field] = None
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'resume'):
                training.validate_resume(bad, identity)

    def test_invalid_config_cannot_run_or_silently_exceed_two_threads(self):
        for kwargs in ({'threads': 3}, {'steps': 0}, {'response_tokens_per_step': 0},
                       {'blocks': 1}, {'response_only': False}, {'optimizer': 'SGD'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                training.TrainConfig(**kwargs)

    def test_release_output_override_does_not_change_seed_budgets(self):
        config = training.TrainConfig.for_profile('release', out=Path('build/custom'))
        self.assertEqual(config.out, Path('build/custom'))
        self.assertEqual(config.token_budget, 262144)

    def test_resume_identity_and_checkpoint_semantics_ignore_output_directory(self):
        first = training.TrainConfig(out=Path('build/first'))
        second = replace(first, out=Path('build/second'))
        a = training.resume_identity(first, 11, {'train': 'a', 'valid': 'b'}, 'tok')
        b = training.resume_identity(second, 11, {'train': 'a', 'valid': 'b'}, 'tok')
        self.assertEqual(a, b)

    def test_resume_validates_emitted_checkpoint_progress_shape(self):
        config = training.TrainConfig(steps=2, response_tokens_per_step=8)
        identity = training.resume_identity(config, 11, {'train': 'a', 'valid': 'b'}, 'tok')
        payload = dict(protocol=identity['protocol'], identity=identity,
                       config=identity['config'], seed=11,
                       versions={'torch': 'x'}, step=1,
                       response_tokens=8, input_tokens=10,
                       loss_curve=[dict(step=1, train_loss=2., response_tokens=8,
                                        input_tokens=10)],
                       validation_curve=[dict(step=1, split='valid', response_nll=1.)],
                       batch_ids_sha256='a' * 64,
                       selected_validation_nll=1., selected_step=1)
        training.validate_resume_progress(payload, identity, {'torch': 'x'})
        import copy
        for field, value in (('input_tokens', -1), ('loss_curve', []),
                             ('batch_ids_sha256', 'bad'), ('selected_step', 9)):
            bad = copy.deepcopy(payload)
            bad[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'resume'):
                training.validate_resume_progress(bad, identity, {'torch': 'x'})

    def test_resume_rejects_impossible_steps_budgets_and_curve_progression(self):
        config = training.TrainConfig(steps=2, response_tokens_per_step=8)
        identity = training.resume_identity(config, 11, {'train': 'a', 'valid': 'b'}, 'tok')
        payload = dict(protocol=identity['protocol'], identity=identity,
                       config=identity['config'], seed=11,
                       versions={'torch': 'x'}, step=1,
                       response_tokens=8, input_tokens=10,
                       loss_curve=[dict(step=1, train_loss=2., response_tokens=8,
                                        input_tokens=10)],
                       validation_curve=[dict(step=1, split='valid', response_nll=1.)],
                       batch_ids_sha256='a' * 64,
                       selected_validation_nll=1., selected_step=1)
        import copy
        impossible = copy.deepcopy(payload)
        impossible.update(step=3, response_tokens=24, input_tokens=26,
                          loss_curve=[dict(step=i, train_loss=2.,
                                           response_tokens=8 * i,
                                           input_tokens=8 * i + 2)
                                      for i in range(1, 4)],
                          validation_curve=[dict(step=i, split='valid', response_nll=1.)
                                            for i in range(1, 4)],
                          selected_step=1)
        broken_budget = copy.deepcopy(payload)
        broken_budget.update(response_tokens=7,
                             loss_curve=[dict(step=1, train_loss=2., response_tokens=7,
                                              input_tokens=10)])
        broken_curve = copy.deepcopy(payload)
        broken_curve.update(step=2, response_tokens=16, input_tokens=20,
                            loss_curve=[dict(step=1, train_loss=2., response_tokens=8,
                                             input_tokens=10),
                                        dict(step=2, train_loss=2., response_tokens=16,
                                             input_tokens=20)],
                            validation_curve=[dict(step=2, split='valid', response_nll=1.)],
                            selected_step=2)
        for bad in (impossible, broken_budget, broken_curve):
            with self.subTest(payload=bad), self.assertRaisesRegex(ValueError, 'resume'):
                training.validate_resume_progress(bad, identity, {'torch': 'x'})

    def test_aggregate_report_artifact_keys_resolve_to_checkpoint_files(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            name = 'checkpoint-seed-11.pt'
            content = b'checkpoint fixture bytes'
            (out / name).write_bytes(content)
            candidate = training.CandidateReport(
                seed=11,
                deterministic={'seed': 11, 'input_tokens': 10, 'response_tokens': 8,
                               'dependency_versions': {'torch': 'x'},
                               'data_hashes': {'train': 'a'},
                               'tokenizer_sha256': 'b'},
                timing={'cpu_seconds': 1., 'wall_seconds': 2.},
                artifacts={name: hashlib.sha256(content).hexdigest()}, checkpoint=name)
            config = training.TrainConfig.for_profile('quick', out=out)
            report = training.write_training_report(config, [candidate])
            saved = json.loads((out / 'training.json').read_text(encoding='utf-8'))
            self.assertEqual(saved, report)
            for artifact_name, expected_hash in saved['hashes']['artifacts'].items():
                artifact = out / artifact_name
                self.assertTrue(artifact.is_file(), artifact_name)
                self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), expected_hash)


class RealCPUTraining(unittest.TestCase):
    def test_finite_losses_exact_budget_and_identical_artifact_hashes(self):
        self.assertIsNotNone(training, 'Portuguese training pipeline is missing')
        # A broken/missing torch is a real failure, never evidence of training.
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            config = training.TrainConfig(steps=2, response_tokens_per_step=8,
                                          out=Path(first))
            a = training.train_candidate(config, 11)
            b = training.train_candidate(replace(config, out=Path(second)), 11)
            self.assertEqual(a.deterministic, b.deterministic)
            self.assertEqual(a.artifacts, b.artifacts)
            self.assertEqual(a.deterministic['response_tokens'], 16)
            self.assertTrue(all(math.isfinite(point['train_loss'])
                                for point in a.deterministic['loss_curve']))
            self.assertTrue(math.isfinite(a.deterministic['selected_validation_nll']))


if __name__ == '__main__':
    unittest.main()
