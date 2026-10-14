"""Tests of the real ELF64 AArch64 inspector used for compiled Android splits."""
import importlib.util
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]/"tools"
sys.path.insert(0, str(TOOLS))
from inspect_arm64_split import analyze_split, dynamic_info, LIBRARIES


class SplitArm64Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("clang") or not shutil.which("ld.lld"):
            raise unittest.SkipTest("clang and lld required for real ARM64 ELF fixture")
        cls.folder = tempfile.TemporaryDirectory()
        p = Path(cls.folder.name)
        (p/"fixture.c").write_text(
            "__attribute__((visibility(\"default\"))) int edge_probe(int v){return v+7;}\n")
        cmd = ["clang", "--target=aarch64-linux-gnu", "-fuse-ld=lld", "-shared",
               "-nostdlib", "-Wl,-soname,libedge_probe.so", "-o",
               str(p/"fixture.so"), str(p/"fixture.c")]
        subprocess.run(cmd, capture_output=True, check=True)
        cls.elf = (p/"fixture.so").read_bytes()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "folder"):
            cls.folder.cleanup()

    def archive(self, root, blobs=None):
        blobs = blobs or {}
        path = root/"config.arm64.apk"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name in LIBRARIES:
                z.writestr("lib/arm64-v8a/" + name, blobs.get(name, self.elf))
        return path

    def test_arm64_elf_three_libraries(self):
        with tempfile.TemporaryDirectory() as d:
            r = analyze_split(self.archive(Path(d)), max_functions=2)
        self.assertEqual(r["status"], "ARM64_APK_STATIC_INVENTORY_PASS", r)
        self.assertEqual(len(r["libraries"]), 3)
        for lib in r["libraries"]:
            self.assertEqual(lib["architecture"], "AArch64")
            self.assertGreater(lib["named_function_symbols"], 0)
            self.assertTrue(any(f["name"]=="edge_probe" for f in lib["function_symbol_sample"]))
            self.assertEqual(lib["soname"], "libedge_probe.so")
            self.assertFalse(r["game_executed"])

    def test_wrong_arch_rejected(self):
        fake=bytearray(self.elf)
        struct.pack_into("<H", fake, 18, 62)
        with tempfile.TemporaryDirectory() as d:
            r=analyze_split(self.archive(Path(d), {"libloader.so": bytes(fake)}))
        self.assertEqual(r["status"], "ARM64_APK_STATIC_INVENTORY_INCOMPLETE")
        self.assertEqual(len(r["libraries"]), 2)

    def test_member_max_size_is_checked(self):
        with tempfile.TemporaryDirectory() as d:
            r=analyze_split(self.archive(Path(d)), max_member=128)
        self.assertEqual(r["status"], "ARM64_APK_STATIC_INVENTORY_INCOMPLETE")
        self.assertEqual(len(r["libraries"]), 0)

    def test_dynamic_section_only_uses_verified_bounds(self):
        data=bytearray(self.elf)
        # e_shoff manipulated out of the binary's mapped range.
        struct.pack_into("<Q", data, 40, len(data) + 100000)
        with self.assertRaises(ValueError):
            dynamic_info(data)


if __name__=="__main__":
    unittest.main()
