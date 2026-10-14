"""Compiled AArch64 shared-object coverage for Unity entry-point inventory."""
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_unity_exports import inventory

class UnityExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("clang") or not shutil.which("ld.lld"):
            raise unittest.SkipTest("clang/lld required to compile real AArch64 ELF")
        cls.folder=tempfile.TemporaryDirectory()
        p=Path(cls.folder.name)
        source=p/"engine.c"
        source.write_text(
            '__attribute__((visibility("default"))) int UnitySendMessage(int x){return x+1;}\n'
            '__attribute__((visibility("default"))) int UnityInitialize(int x){\n'
            ' if(x<0) return 0; return UnitySendMessage(x); }\n'
            '__attribute__((visibility("default"))) int UnityShutdown(int x){return x-1;}\n'
            '__attribute__((visibility("default"))) int JNI_OnLoad(int x){return x+7;}\n')
        lib=p/"libunity.so"
        subprocess.run(["clang","--target=aarch64-linux-gnu","-fuse-ld=lld",
            "-O0","-shared","-nostdlib","-fno-inline","-o",str(lib),str(source)],
            check=True,capture_output=True)
        cls.lib=lib.read_bytes()
    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"folder"):cls.folder.cleanup()

    def make_apk(self,p):
        with zipfile.ZipFile(p,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("lib/arm64-v8a/libunity.so",self.lib)
        return p

    def test_real_compiler_generated_engine_exports(self):
        with tempfile.TemporaryDirectory() as d:
            out=inventory(self.make_apk(Path(d)/"engine.apk"))
        self.assertEqual(out["status"],"AARCH64_UNITY_ENGINE_STATIC_EXPORTS_PASS")
        self.assertEqual(out["function_count"],4)
        self.assertTrue(all(f["size_bytes"]>=4 for f in out["functions"]))
        self.assertTrue(any(f["control_transfers"]>0 for f in out["functions"]))
        self.assertFalse(out["executed_original_game"])
        self.assertFalse(out["unity_camera_located"])

    def test_reject_duplicate_function_set(self):
        with self.assertRaisesRegex(ValueError,"unique"):
            inventory("not-an-apk",("UnitySendMessage","UnitySendMessage"))

    def test_reject_unexpected_function(self):
        with self.assertRaisesRegex(ValueError,"only known"):
            inventory("not-an-apk",("PlayerManager",))

if __name__=="__main__": unittest.main()
