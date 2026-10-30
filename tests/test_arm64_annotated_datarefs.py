"""Real LLVM symbol-annotated PC-relative target parsing regression."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgeai_arm64_datarefs import analyze_text


class AnnotatedTargetTests(unittest.TestCase):
    def test_annotated_adrp_is_traced_through_add(self):
        text = ("00000000000e3950 <.text>:\n"
                " e3954: adrp x0, 0x33e000 <dl_iterate_phdr@plt+0xb0>\n"
                " e3958: add x0, x0, #0xf60\n")
        refs = analyze_text(text)["references"]
        self.assertEqual([(r["kind"], r["address"]) for r in refs],
                         [("computed_address", "0x33ef60")])

    def test_annotated_adr_can_be_dereferenced(self):
        text = ("0000000000001000 <fn>:\n"
                " 1000: adr x4, 0x2050 <object+0x10>\n"
                " 1004: ldr x5, [x4, #8]\n")
        refs = analyze_text(text)["references"]
        self.assertEqual([r["address"] for r in refs], ["0x2058"])

    def test_unknown_symbolic_target_is_not_guessed(self):
        text = ("0000000000001000 <fn>:\n"
                " 1000: adrp x4, x7 <unknown>\n"
                " 1004: ldr x5, [x4]\n")
        self.assertEqual(analyze_text(text)["references"], [])


if __name__ == "__main__":
    unittest.main()
