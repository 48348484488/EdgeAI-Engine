"""V32 regression: real native bundle attestation and orphan-process cleanup."""
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import textwrap
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from edgeai_v15_watchdog import run

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = '''import argparse, hashlib, json, subprocess
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('elf'); p.add_argument('--output-dir'); p.add_argument('--enable-stateful-printf', action='store_true'); a=p.parse_args()
o=Path(a.output_dir)
(o/'candidate_2000.cpp').write_text('extern "C" int recovered_2000(){return 7;}')
(o/'candidate_3000.cpp').write_text('extern "C" int recovered_2000(); extern "C" int recovered_3000(){return recovered_2000();}')
subprocess.run(['g++','-std=c++17','-O2','-fPIC','-shared','-Wl,-z,defs',str(o/'candidate_2000.cpp'),str(o/'candidate_3000.cpp'),'-o',str(o/'recovered_candidates.so')],check=True)
r={'binary_sha256':hashlib.sha256(Path(a.elf).read_bytes()).hexdigest(),'source_read':False,'symbols_used':False,'compile_status':'SUCCEEDED','cpp_emitted_candidate_count':2,'functions':[{'address':'0x2000','status':'CPP_EMITTED_NOT_BEHAVIORALLY_VALIDATED'},{'address':'0x3000','status':'CPP_EMITTED_NOT_BEHAVIORALLY_VALIDATED'}]}
(o/'coverage.json').write_text(json.dumps(r))
'''


class V32Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.elf = self.root/'fixture.elf'
        self.elf.write_bytes(b'v32 fixture only')
        self.sha = hashlib.sha256(self.elf.read_bytes()).hexdigest()
        self.tool = self.root/'tools'
        self.tool.mkdir()
        self.dest = self.root/'bundle'
        for name in ('edgeai_2048_bundle_verify.py','edgeai_cpp_link_gate.py'):
            shutil.copyfile(ROOT/'tools'/name, self.tool/name)
        (self.tool/'aarch64_multistage_batch.py').write_text(GENERATOR)
        shutil.copyfile(ROOT/'tools'/'edgeai_2048_v15_recovery.py',
                        self.tool/'edgeai_2048_v15_recovery_impl.py')

    def driver(self, code):
        (self.tool/'edgeai_2048_v15_recovery.py').write_text(textwrap.dedent(code))

    def test_real_compiled_bundle_passes_independent_audit(self):
        self.driver('''
            import argparse, hashlib
            from pathlib import Path
            from edgeai_2048_v15_recovery_impl import rebuild
            p=argparse.ArgumentParser()
            p.add_argument('elf'); p.add_argument('--destination'); p.add_argument('--tool-dir'); p.add_argument('--timeout')
            a=p.parse_args()
            digest=hashlib.sha256(Path(a.elf).read_bytes()).hexdigest()
            rebuild(a.elf, a.destination, a.tool_dir, expected_count=2, expected_elf_sha256=digest)
        ''')
        result = run(self.elf,self.dest,self.tool,timeout=15,heartbeat=.05,expected_sha256=self.sha)
        self.assertEqual(result['status'],'SUCCEEDED',result)
        self.assertTrue(result['independent_bundle_verification_passed'])
        self.assertEqual(result['native_exports_verified'],2)
        self.assertTrue((self.dest/'recovered_candidates.so').is_file())

    @unittest.skipUnless(os.name=='posix','requires POSIX process groups')
    def test_orphan_child_cannot_survive_driver_exit(self):
        marker = self.root/'orphan_survived.txt'
        child_code = f'import pathlib,time; time.sleep(1); pathlib.Path({str(marker)!r}).write_text("SURVIVED")'
        self.driver(f'''
            import subprocess, sys, pathlib, time
            subprocess.Popen([sys.executable,'-c',{child_code!r}])
            time.sleep(.2)
            dest=pathlib.Path(sys.argv[sys.argv.index('--destination')+1])
            dest.mkdir()
            (dest/'bundle_manifest.json').write_text('{{}}')
        ''')
        result=run(self.elf,self.dest,self.tool,timeout=5,heartbeat=.05,expected_sha256=self.sha)
        self.assertEqual(result['status'],'FAILED',result)
        time.sleep(1.2)
        self.assertFalse(marker.exists(),'orphan child escaped watchdog process group')
        self.assertFalse(self.dest.exists())

    def test_independent_verifier_rejects_fake_success(self):
        self.driver('''
            import pathlib, sys
            dest=pathlib.Path(sys.argv[sys.argv.index('--destination')+1])
            dest.mkdir()
            (dest/'bundle_manifest.json').write_text('{"schema_version":2}')
        ''')
        result=run(self.elf,self.dest,self.tool,timeout=5,heartbeat=.05,expected_sha256=self.sha)
        self.assertEqual(result['status'],'FAILED',result)
        self.assertFalse(result['independent_bundle_verification_passed'])
        self.assertFalse(self.dest.exists())


if __name__=='__main__':
    unittest.main()
