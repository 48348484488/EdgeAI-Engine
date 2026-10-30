"""Regression checks for conservative AArch64 GPR pair data references."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgeai_arm64_datarefs import analyze_text


def references(instructions):
    disassembly = "0000000000001000 <sample>:\n" + "\n".join(
        f" {0x1000 + 4 * i:x}: {line}" for i, line in enumerate(instructions)
    )
    return analyze_text(disassembly)["references"]


class PairReferenceTests(unittest.TestCase):
    def test_x_register_store_pair_produces_two_addresses(self):
        refs = references(["adrp x2, 0x2000", "stp x0, x1, [x2, #16]"])
        self.assertEqual([(r["kind"], r["address"], r.get("width_bytes"))
                          for r in refs],
                         [("store", "0x2010", 8), ("store", "0x2018", 8)])
        self.assertEqual([r["pair_index"] for r in refs], [0, 1])

    def test_w_register_load_pair_uses_four_byte_stride(self):
        refs = references(["adrp x2, 0x2000", "ldp w0, w1, [x2, #8]"])
        self.assertEqual([r["address"] for r in refs], ["0x2008", "0x200c"])
        self.assertTrue(all(r["width_bytes"] == 4 for r in refs))

    def test_signed_pair_load_and_negative_offset(self):
        refs = references(["adrp x2, 0x3000", "ldpsw x0, x1, [x2, #-8]"])
        self.assertEqual([r["address"] for r in refs], ["0x2ff8", "0x2ffc"])

    def test_writeback_pair_is_not_guessed_and_invalidates_base(self):
        refs = references(["adrp x2, 0x2000",
                           "ldp x0, x1, [x2, #16]!",
                           "ldr x4, [x2]"])
        self.assertEqual(refs, [])

    def test_pair_load_invalidates_both_destinations(self):
        refs = references(["adrp x0, 0x2000",
                           "mov x1, x0",
                           "ldp x0, x1, [x0]",
                           "ldr x4, [x0]",
                           "ldr x5, [x1]"])
        self.assertEqual([r["address"] for r in refs], ["0x2000", "0x2008"])

    def test_simd_pair_not_incorrectly_treated_as_gpr(self):
        refs = references(["adrp x2, 0x2000", "ldp q0, q1, [x2]"])
        self.assertEqual(refs, [])


if __name__ == "__main__":
    unittest.main()
