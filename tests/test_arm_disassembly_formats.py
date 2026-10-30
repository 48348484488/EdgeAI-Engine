"""The shared ARM32 decoder must accept LLVM output formats without guessing semantics."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from recover_winner import INSTRUCTION, instructions_for


class ARMDisassemblyFormatTests(unittest.TestCase):
    def test_raw_word_spaced_bytes_thumb_and_no_raw(self):
        examples = [
            ("1000: e92d4830      push {r4, r5, r11, lr}", "push"),
            ("1000: 30 48 2d e9    push {r4, r5, r11, lr}", "push"),
            ("1000: 00 bf         nop", "nop"),
            ("1000: bl 0x1010 <play>", "bl"),
        ]
        for line, opcode in examples:
            with self.subTest(line=line):
                match = INSTRUCTION.fullmatch(line)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(2), opcode)
        self.assertIsNone(INSTRUCTION.fullmatch("1000: 00000000"))

    def test_instruction_extraction_is_format_invariant(self):
        for prefix in ("e92d4830 ", "30 48 2d e9 ", ""):
            with self.subTest(prefix=prefix):
                dump = (
                    "00001000 <winner>:\n"
                    f" 1000: {prefix}push {{r4, r5, r11, lr}}\n"
                    f" 1004: {prefix}pop {{r4, r5, r11, pc}}\n"
                    "00001008 <other>:\n 1008: bx lr\n"
                )
                rows = instructions_for(dump, "winner")
                self.assertEqual([r["op"] for r in rows], ["push", "pop"])
                self.assertEqual([r["pc"] for r in rows], [0x1000, 0x1004])

    def test_reject_missing_label(self):
        with self.assertRaisesRegex(ValueError, "winner function symbol missing"):
            instructions_for("1000: bl 0x1020", "winner")


if __name__ == "__main__":
    unittest.main()
