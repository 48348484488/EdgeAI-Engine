import importlib.util
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'benchmarks')]
from run_goals import stage_commands

class WorkflowV07(unittest.TestCase):
    def test_profile_is_executable(self):
        try:stages=stage_commands('instructions-quick',ROOT/'build',1)
        except ValueError:stages=[]
        self.assertGreaterEqual(len(stages),9,'missing instruction goal executor')
        self.assertEqual(len({n for n,c in stages}),len(stages))
        for name,command in stages:
            self.assertTrue(command)
            self.assertTrue(all(isinstance(c,str) for c in command))

    def test_energy_workload_accepts_instruction_models(self):
        stages=dict(stage_commands('instructions',ROOT/'build',1))
        self.assertIn(str(ROOT/'build'/'edgeai_generate'),stages['energy_probe'])

    def test_scoring_separates_empty_eos_from_correctness(self):
        self.assertIsNotNone(importlib.util.find_spec('instruction_eval_v07'))
        from instruction_eval_v07 import summarize
        rows=[dict(task='copy',language='pt',split='test_id',exact=False,correct=False,stopped_on_eos=True,generated_tokens=1,total_seconds=.001),
              dict(task='copy',language='pt',split='test_id',exact=True,correct=True,stopped_on_eos=False,generated_tokens=32,total_seconds=.003)]
        r=summarize(rows)
        self.assertEqual(r['correct'],1);self.assertEqual(r['exact'],1)
        self.assertEqual(r['eos'],1);self.assertEqual(r['correct_and_eos'],0)

if __name__=='__main__':unittest.main()
