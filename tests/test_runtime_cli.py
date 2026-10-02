import os
import json, subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BINARY=Path(os.environ.get('EDGEAI_BUILD_DIR',str(ROOT/'build')))/'edgeai_runtime_benchmark'
class RuntimeCLI(unittest.TestCase):
    def test_cpu_metric_and_kernel(self):
        model=ROOT/'models/hybrid_tiny.edge'
        for k in ('scalar','auto'):
            run=subprocess.run([str(BINARY),str(model),'100',k],capture_output=True,text=True,check=True)
            data=json.loads(run.stdout)
            self.assertIn('cpu_seconds',data)
            self.assertGreaterEqual(data['cpu_seconds'],0)
            self.assertEqual(data['requested_kernel'],k)
            self.assertEqual(data['tokens'],100)
            self.assertIsNone(data['energy_joules'])
    def test_rejects_bad_arguments(self):
        model=ROOT/'models/hybrid_tiny.edge'
        for n,k in [('0','auto'),('-1','auto'),('20oops','auto'),('100','fake')]:
            run=subprocess.run([str(BINARY),str(model),n,k],capture_output=True)
            self.assertNotEqual(run.returncode,0,(n,k))
if __name__=='__main__':
    if len(sys.argv)>1 and not sys.argv[1].startswith('-'):
        BINARY=Path(sys.argv.pop(1)).resolve()
    unittest.main()
