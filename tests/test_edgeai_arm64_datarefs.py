"""Conservative ARM64 global data-reference discovery regression tests."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from edgeai_arm64_datarefs import analyze_text, analyze_elf

# Generated from a real Clang AArch64 linked ELF:
# volatile int global_counter = 41;
# __attribute__((noinline)) int tick(int n) { return global_counter + n; }
CLANG_ARM64 = """
0000000000400000 <tick>:
  400000: adrp x8, 0x430000
  400004: ldr w8, [x8, #0x130]
  400008: add w0, w8, w0
  40000c: ret
"""


class Arm64DataReferenceTests(unittest.TestCase):
    def test_real_clang_adrp_ldr_reference(self):
        report = analyze_text(CLANG_ARM64)
        self.assertEqual(report["static_reference_count"], 1)
        self.assertEqual(report["references"][0]["address"], "0x430130")
        self.assertEqual(report["references"][0]["kind"], "load")
        self.assertEqual(report["references"][0]["origin_pc"], "0x400000")

    def test_adrp_add_store_and_register_copy(self):
        asm = """
0000000000400000 <update>:
  400000: adrp x0, 0x430000
  400004: add x0, x0, #0x130
  400008: mov x9, x0
  40000c: str w1, [x9, #0x4]
  400010: ret
"""
        refs = analyze_text(asm)["references"]
        self.assertEqual([(r["kind"], r["address"]) for r in refs],
                         [("computed_address", "0x430130"), ("store", "0x430134")])

    def test_calls_and_unknown_writes_invalidate_dataflow(self):
        asm = """
0000000000400000 <tick>:
  400000: adrp x8, 0x430000
  400004: bl 0x401000
  400008: ldr w0, [x8, #0x130]
  40000c: adrp x8, 0x430000
  400010: eor x8, x8, x1
  400014: ldr w0, [x8, #0x130]
  400018: ret
"""
        self.assertEqual(analyze_text(asm)["references"], [])

    def test_no_guess_for_dynamic_offset_or_function_merge(self):
        asm = """
0000000000400000 <tick>:
  400000: adrp x8, 0x430000
  400004: ldr w0, [x8, x1]
  400008: b.eq 0x400014
  40000c: ldr w0, [x8, #0x130]
  400010: ret
"""
        self.assertEqual(analyze_text(asm)["references"], [])

    def test_relocatable_object_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.o"
            header = bytearray(20)
            header[:6] = bytes([127, 69, 76, 70, 2, 1])
            header[16:18] = (1).to_bytes(2, "little")
            header[18:20] = (183).to_bytes(2, "little")
            path.write_bytes(header)
            with self.assertRaisesRegex(ValueError, "requires linked ARM64"):
                analyze_elf(path)


if __name__ == "__main__":
    unittest.main()
