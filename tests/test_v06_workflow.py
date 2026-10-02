import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class NativeToolGate(unittest.TestCase):
    def test_native_text_evaluator_source_exists(self):
        self.assertTrue((ROOT/'tools/text_eval.cpp').is_file(),'native same-byte evaluation missing')
    def test_native_tokenizer_source_exists(self):
        self.assertTrue((ROOT/'tools/tokenize.cpp').is_file(),'native token trace missing')
if __name__=='__main__':unittest.main()
sys.path.insert(0,str(ROOT/'tools'))
class IndependentGoals(unittest.TestCase):
    def test_independent_profile_covers_evidence_gates(self):
        from run_goals import stage_commands
        try:stages=dict(stage_commands('independent',ROOT/'build',1))
        except ValueError:stages={}
        for gate in ['snapshot_integrity','train_only_tokenizer','bpe_parity','equal_cpu_external_training','native_external','capability_tasks','energy_probe','validate_reports']:
            self.assertIn(gate,stages)
