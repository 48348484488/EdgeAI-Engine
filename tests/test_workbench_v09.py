import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
BUILD=Path(os.environ.get('EDGEAI_BUILD_DIR',ROOT/'build'))
sys.path.insert(0,str(ROOT/'tools'))
class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('workbench'),'workbench missing')
    def test_search_json_real_lines(self):
        from workbench import search_code
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a.pwn';p.write_text('stock RecuperarConta(id) {\n return id;\n}\n')
            r=search_code(Path(td),'RecuperarConta',build=BUILD)
            self.assertEqual(r['hits'][0]['match_line'],1)
            self.assertEqual(r['hits'][0]['path'],'a.pwn')
            self.assertFalse(r['neural_used'])
    def test_native_answer_and_runtime_metadata(self):
        from workbench import native_ask
        r=native_ask('Copie exatamente: aaeb',ROOT/'models/instructions_v07/default.edge',build=BUILD)
        self.assertEqual(r['text'],'aaeb');self.assertEqual(r['output_hex'],'61616562')
        self.assertTrue(r['native_metrics']['stopped_on_eos']);self.assertIsNone(r['energy_joules'])
    def test_raw_scoring_does_not_turn_errors_into_success(self):
        from workbench import score_answer
        self.assertTrue(score_answer({'output_hex':b'a'.hex()},'a'))
        self.assertFalse(score_answer({'error':'missing'},''))
        self.assertFalse(score_answer({'output_hex':b'a '.hex()},'a'))
    def test_no_reference_is_reported_as_not_requested(self):
        from workbench import compare
        cases=[{'id':'copy','prompt':'Copie exatamente: aaeb','expected':'aaeb'}]
        r=compare(cases,ROOT/'models/instructions_v07/default.edge',build=BUILD)
        self.assertEqual(r['reference']['status'],'not_requested')
        self.assertIsNone(r['reference']['accuracy'])
        self.assertEqual(r['native']['correct'],1)
    def test_case_validation(self):
        from workbench import validate_cases
        for rows in [[],[{'id':'x'}],[{'id':'x','prompt':'x','expected':'x'}]*2]:
            with self.assertRaises(ValueError):validate_cases(rows)
    def test_cli_errors_nonzero_no_shell(self):
        p=subprocess.run([sys.executable,str(ROOT/'tools/workbench.py'),'ask','x','--backend','reference','--server','http://example.com/v1'],capture_output=True)
        self.assertNotEqual(p.returncode,0)
    def test_search_cli_limits_and_json(self):
        for args in [['--limit','0'],['--limit','99'],['--context','11'],['--limit','x']]:
            p=subprocess.run([str(BUILD/'edgeai_code_search'),str(ROOT/'src'),'greedy_token',*args],capture_output=True)
            self.assertNotEqual(p.returncode,0)
    def test_reference_unavailable_is_not_scored_as_wrong_answer(self):
        from workbench import compare
        import socket
        s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
        r=compare([{'id':'x','prompt':'x','expected':'x'}],ROOT/'models/instructions_v07/default.edge',build=BUILD,reference_url=f'http://127.0.0.1:{port}/v1')
        self.assertEqual(r['reference']['status'],'unavailable');self.assertIsNone(r['reference']['accuracy'])
if __name__=='__main__':unittest.main()
