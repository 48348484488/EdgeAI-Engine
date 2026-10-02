import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
class GoalsV09(unittest.TestCase):
 def test_useful_profile_does_not_train_download_or_require_server(self):
  from run_goals import stage_commands
  stages=dict(stage_commands('useful',ROOT/'build',1))
  for name in ('cpp_tests','python_tests','source_retrieval','native_diagnostic','reference_contracts','energy_probe','package_smoke'):self.assertIn(name,stages)
  all_cmd=' '.join(' '.join(cmd) for cmd in stages.values())
  self.assertNotIn('--reference-url',all_cmd);self.assertNotIn('train_',all_cmd)
 def test_profile_commands_are_no_shell_lists(self):
  from run_goals import stage_commands
  for name,cmd in stage_commands('useful',ROOT/'build',1):
   self.assertTrue(name);self.assertIsInstance(cmd,list);self.assertTrue(all(isinstance(x,str) for x in cmd))
if __name__=='__main__':unittest.main()
