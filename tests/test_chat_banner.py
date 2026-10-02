import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BINARY=Path(os.environ.get('EDGEAI_BUILD_DIR',str(ROOT/'build')))/'edgeai_chat'


class ChatBanner(unittest.TestCase):
    def test_banner_reports_v012_and_edgeai8(self):
        run=subprocess.run(
            [str(BINARY),'--memory',':memory:'],
            input='sair\n',text=True,capture_output=True,check=True)
        self.assertIn('EdgeAI Engine v0.12 (model formats through EDGEAI8)',run.stdout)


if __name__=='__main__':
    if len(sys.argv)>1 and not sys.argv[1].startswith('-'):
        BINARY=Path(sys.argv.pop(1)).resolve()
    unittest.main()
