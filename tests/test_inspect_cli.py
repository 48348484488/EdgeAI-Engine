import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BINARY=Path(os.environ.get('EDGEAI_BUILD_DIR',str(ROOT/'build')))/'edgeai_inspect'


def inspect(path):
    run=subprocess.run([str(BINARY),str(path)],capture_output=True,text=True,check=True)
    out={}
    for line in run.stdout.splitlines():
        if '=' in line:
            k,v=line.split('=',1)
            out[k]=v
    return out


class InspectCLI(unittest.TestCase):
    def test_reports_edgeai8_and_multiblock_memory(self):
        one=inspect(ROOT/'models/v012/seed11-b1-after.edge')
        two=inspect(ROOT/'models/v012/seed11-b2-after.edge')
        self.assertEqual(one['format'],'EDGEAI7')
        self.assertEqual(two['format'],'EDGEAI8')
        self.assertEqual(int(two['sequence_state_payload_bytes']),2*int(one['sequence_state_payload_bytes']))
        self.assertGreater(int(two['numeric_working_bytes']),int(one['numeric_working_bytes']))


if __name__=='__main__':
    if len(sys.argv)>1 and not sys.argv[1].startswith('-'):
        BINARY=Path(sys.argv.pop(1)).resolve()
    unittest.main()
