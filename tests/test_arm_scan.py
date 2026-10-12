"""Regression tests for conservative ARM32/Thumb16 branch scanner."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location(
    "arm_scan", Path(__file__).resolve().parents[1] / "tools" / "arm_scan.py")
arm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arm)

def elf(code):
    b = bytearray(0x100 + len(code))
    b[:16] = b"\x7fELF" + bytes([1, 1, 1]) + bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH", b, 16, 2, 40, 1, 0x1000, 52, 0, 0, 52, 32, 1, 0, 0, 0)
    struct.pack_into("<IIIIIIII", b, 52, 1, 0x100, 0x1000, 0, len(code), len(code), 5, 4)
    b[0x100:] = code
    return b

class Tests(unittest.TestCase):
    def test_arm_bl(self):
        d = elf(struct.pack("<I", 0xeb000000))
        self.assertEqual(arm.scan(d)["branches"][0], {
            "address": "0x1000", "instruction": "BL", "target": "0x1008"})
    def test_arm_backwards(self):
        d = elf(struct.pack("<I", 0xeafffffe))
        self.assertEqual(arm.scan(d)["branches"][0]["target"], "0x1000")
    def test_thumb_cond(self):
        d = elf(struct.pack("<H", 0xd0fe))
        self.assertEqual(arm.scan(d, "thumb")["branches"][0]["target"], "0x1000")
    def test_thumb_unconditional(self):
        d = elf(struct.pack("<H", 0xe7fe))
        self.assertEqual(arm.scan(d, "thumb")["branches"][0]["target"], "0x1000")
    def test_reject_x86(self):
        d = elf(b"\0" * 4)
        struct.pack_into("<H", d, 18, 3)
        with self.assertRaises(arm.ScanError):
            arm.scan(d)
    def test_no_exec(self):
        d = elf(struct.pack("<I", 0xeb000000))
        struct.pack_into("<I", d, 52 + 24, 4)
        self.assertEqual(arm.scan(d)["branch_count"], 0)
    def test_bad_range(self):
        d = elf(b"\0" * 4)
        struct.pack_into("<I", d, 52 + 16, 999999)
        with self.assertRaises(arm.ScanError):
            arm.scan(d)
    def test_mode(self):
        with self.assertRaises(arm.ScanError):
            arm.scan(elf(b"\0" * 4), "auto")

if __name__ == "__main__":
    unittest.main()
