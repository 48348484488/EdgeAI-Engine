import os
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BUILD=Path(os.environ.get('EDGEAI_BUILD_DIR',str(ROOT/'build')))
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'benchmarks')]
class WorkflowTests(unittest.TestCase):
    def test_goal_definitions_and_no_shell(self):
        self.assertIsNotNone(importlib.util.find_spec('run_goals'),'run_goals must exist')
        import run_goals
        stages=run_goals.stage_commands('quick',ROOT/'build',1)
        self.assertGreaterEqual(len(stages),6)
        self.assertEqual(len({n for n,c in stages}),len(stages))
        for name,cmd in stages:
            self.assertIsInstance(cmd,list);self.assertTrue(all(isinstance(t,str) for t in cmd))
    def test_research_goals_include_equal_cpu_followup_and_final_parity(self):
        import run_goals
        stages=dict(run_goals.stage_commands('research',ROOT/'build',1))
        self.assertIn('equal_cpu_training',stages)
        self.assertIn('trained_parity',stages)
        self.assertIn('equal_cpu_parity',stages)
        self.assertIn('equal_cpu_native',stages)
        self.assertIn('energy_probe',stages)
        self.assertIn('--cpu-seconds',stages['equal_cpu_training'])
        self.assertIn('12',stages['equal_cpu_training'])
    def test_interactive_cli_reports_current_version(self):
        result=subprocess.run([str(BUILD/'edgeai_chat'),'--memory',':memory:'],input='sair\n',capture_output=True,text=True,check=True)
        import re
        version=re.search(r'project\(EdgeAIEngine VERSION (\d+\.\d+)\.', (ROOT/'CMakeLists.txt').read_text()).group(1)
        self.assertIn('EdgeAI Engine v'+version,result.stdout)
    def test_cache_checks_identity_and_artifact_content(self):
        from language_v05 import reusable,trial_signature
        from language_data import sha256
        with tempfile.TemporaryDirectory(dir=ROOT/'results') as td:
            path=Path(td)/'model.edge';path.write_bytes(b'model');signature=trial_signature({'a':1})
            row={'signature':signature,'artifacts':{str(path.relative_to(ROOT)):sha256(b'model')}}
            self.assertTrue(reusable(row,signature));self.assertFalse(reusable(row,'different'))
            path.write_bytes(b'damaged');self.assertFalse(reusable(row,signature))
    def test_native_evaluator_rejects_malformed_blocks(self):
        binary=BUILD/'edgeai_evaluate';model=ROOT/'models/hybrid_tiny.edge'
        for raw in (b'',b'EDGBLK1\0'+struct.pack('<I',0),b'EDGBLK1\0'+struct.pack('<II',1,64)+b'short'):
            with tempfile.TemporaryDirectory() as td:
                p=Path(td)/'blocks.bin';p.write_bytes(raw)
                proc=subprocess.run([str(binary),str(model),str(p)],capture_output=True)
                self.assertNotEqual(proc.returncode,0)
    def test_native_evaluator_count_and_reset(self):
        from language_data import write_blocks,make_blocks
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'blocks.bin';write_blocks(make_blocks([b'abcde',b'abcde'],4),p)
            proc=subprocess.run([str(BUILD/'edgeai_evaluate'),str(ROOT/'models/hybrid_tiny.edge'),str(p)],capture_output=True,text=True,check=True)
            row=json.loads(proc.stdout);self.assertEqual(row['targets'],8);self.assertEqual(row['blocks'],2);self.assertTrue(row['reset_between_blocks'])
if __name__=='__main__':unittest.main()
