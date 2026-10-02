import subprocess
import sys
import unittest
from pathlib import Path

BINARY=Path(sys.argv.pop(1)).resolve() if len(sys.argv)>1 and not sys.argv[1].startswith('-') else Path('edgeai_chat')


class ChatBanner(unittest.TestCase):
    def test_banner_reports_v012_and_edgeai8(self):
        run=subprocess.run(
            [str(BINARY),'--memory',':memory:'],
            input='sair\n',text=True,capture_output=True,check=True)
        self.assertIn('EdgeAI Engine v0.12 (model formats through EDGEAI8)',run.stdout)


if __name__=='__main__':
    unittest.main()
