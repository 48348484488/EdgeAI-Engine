"""Unit tests for conservative AArch64 ELF64 function branch inventory."""
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_branch_map import decode, analyze, analyze_split, ELFError


class Arm64BranchMapTests(unittest.TestCase):
    def test_pc_relative_direct_branch_offsets(self):
        cases = [
            (0x14000002, "B", 0x1008),
            (0x94000001, "BL", 0x1004),
            (0x17ffffff, "B", 0x0ffc),
            (0x54000040, "B.cond", 0x1008),
            (0x34000040, "CBZ", 0x1008),
            (0x35000040, "CBNZ", 0x1008),
            (0x36000040, "TBZ", 0x1008),
            (0x37000040, "TBNZ", 0x1008),
            (0xd65f03c0, "RET", None),
            (0xd61f0000, "BR", None),
            (0xd63f0000, "BLR", None),
        ]
        for word, kind, target in cases:
            with self.subTest(kind=kind,word=hex(word)):
                r=decode(word,0x1000)
                self.assertIsNotNone(r)
                self.assertEqual(r["kind"],kind)
                self.assertEqual(r["target"],target)
        self.assertIsNone(decode(0xd503201f,0x1000))  # NOP not a control transfer

    @classmethod
    def setUpClass(cls):
        if not shutil.which("clang") or not shutil.which("ld.lld"):
            raise unittest.SkipTest("clang/lld required for AArch64 binary fixture")
        cls.tmp=tempfile.TemporaryDirectory()
        root=Path(cls.tmp.name)
        source=root/"fixture.c"
        source.write_text(
            '__attribute__((noinline)) int callee(int x){return x+5;}\n'
            '__attribute__((visibility("default"))) int JNI_OnLoad(int x){\n'
            '  if (x == 0) return 11;\n'
            '  return callee(x);\n'
            '}\n'
        )
        cls.lib=root/"libloader.so"
        subprocess.run(["clang","--target=aarch64-linux-gnu","-fuse-ld=lld",
            "-O0","-shared","-nostdlib","-fno-inline","-o",str(cls.lib),str(source)],
            check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"tmp"):cls.tmp.cleanup()

    def test_real_compiled_elf_has_control_transfers(self):
        data=self.lib.read_bytes()
        r=analyze(data,"JNI_OnLoad")
        self.assertGreater(r["size_bytes"],0)
        self.assertGreater(r["decoded_control_transfers"],0)
        self.assertTrue(r["counts"].get("RET",0)>=1)
        self.assertFalse(r["code_executed"])

    def test_reject_wrong_machine(self):
        data=bytearray(self.lib.read_bytes())
        struct.pack_into("<H",data,18,62)
        with self.assertRaises(ELFError):
            analyze(data,"JNI_OnLoad")

    def test_zip_extraction_reads_exact_file(self):
        with tempfile.TemporaryDirectory() as d:
            apk=Path(d)/"split.apk"
            with zipfile.ZipFile(apk,"w",zipfile.ZIP_DEFLATED) as z:
                z.writestr("lib/arm64-v8a/libloader.so",self.lib.read_bytes())
            self.assertEqual(analyze_split(apk)["function"],"JNI_OnLoad")


if __name__=="__main__": unittest.main()
