import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BINARY=Path(os.environ.get('EDGEAI_BUILD_DIR',str(ROOT/'build')))/'edgeai_chat'


class ChatBanner(unittest.TestCase):
    def test_banner_reports_v016_and_edgeai8(self):
        run=subprocess.run(
            [str(BINARY),'--memory',':memory:'],
            input='sair\n',text=True,capture_output=True,check=True)
        self.assertIn('EdgeAI Engine v0.16 (model formats through EDGEAI8)',run.stdout)


    def test_prompt_metadata_reports_route(self):
        calc=subprocess.run(
            [str(BINARY),'--memory',':memory:','--prompt','2 + 2'],
            text=True,capture_output=True,check=True)
        self.assertIn('[route=calculator neural=0 ',calc.stdout)
        neural=subprocess.run(
            [str(BINARY),'--memory',':memory:','--prompt','hello there'],
            text=True,capture_output=True,check=True)
        self.assertIn('[route=neural neural=1 ',neural.stdout)


if __name__=='__main__':
    if len(sys.argv)>1 and not sys.argv[1].startswith('-'):
        BINARY=Path(sys.argv.pop(1)).resolve()
    unittest.main()
