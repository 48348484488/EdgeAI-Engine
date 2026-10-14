"""Real AArch64 compiled symbol triage with explicit negative test."""
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_symbol_triage import triage


class SymbolTriageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("clang") or not shutil.which("ld.lld"):
            raise unittest.SkipTest("clang/lld are needed to test a real ARM64 ELF")
        cls.tmp=tempfile.TemporaryDirectory()
        root=Path(cls.tmp.name)
        (root/"fixture.c").write_text(
            '__attribute__((visibility("default"))) int CameraController(int n){return n;}\n'
            '__attribute__((visibility("default"))) int playerNetworkObserver(int n){return n+1;}\n'
            '__attribute__((visibility("default"))) int opaque_123(int n){return n+2;}\n')
        so=root/"game.so"
        subprocess.run(["clang","--target=aarch64-linux-gnu","-fuse-ld=lld",
            "-shared","-nostdlib","-O0","-o",str(so),str(root/"fixture.c")],
            check=True,capture_output=True)
        cls.so=so.read_bytes()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"tmp"): cls.tmp.cleanup()

    def make_apk(self,folder,data=None):
        p=folder/"split.apk"
        with zipfile.ZipFile(p,"w",zipfile.ZIP_STORED) as z:
            z.writestr("lib/arm64-v8a/libil2cpp.so",self.so if data is None else data)
        return p

    def test_camera_player_network_symbols_detected(self):
        with tempfile.TemporaryDirectory() as d:
            r=triage(self.make_apk(Path(d)))
        self.assertEqual(r["status"],"ARM64_ELF_SYMBOL_NAME_TRIAGE_PASS")
        self.assertEqual(r["terms"]["camera"]["named_function_matches"],1)
        self.assertEqual(r["terms"]["player"]["named_function_matches"],1)
        self.assertEqual(r["terms"]["network"]["named_function_matches"],1)
        self.assertEqual(r["terms"]["position"]["named_function_matches"],0)
        self.assertEqual(r["gameplay_functions_confirmed"],0)
        self.assertFalse(r["code_executed"])

    def test_truncated_example_list_counts_still_complete(self):
        with tempfile.TemporaryDirectory() as d:
            r=triage(self.make_apk(Path(d)),max_per_term=0)
        self.assertEqual(r["terms"]["camera"]["named_function_matches"],1)
        self.assertTrue(r["terms"]["camera"]["examples_truncated"])
        self.assertFalse(r["terms"]["camera"]["examples"])

    def test_bad_machine_rejected(self):
        raw=bytearray(self.so)
        raw[18:20]=(62).to_bytes(2,"little")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                triage(self.make_apk(Path(d),bytes(raw)))


if __name__=="__main__":unittest.main()
