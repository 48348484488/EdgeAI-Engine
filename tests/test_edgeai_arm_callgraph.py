"""Regression tests for generic ARM32/ARM64 static call-graph discovery."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from edgeai_arm_callgraph import analyze_text, elf_architecture

ARM32 = """
00001000 <game_update>:
    1000: bl 0x1080 <player_move>
    1004: blx r3
    1008: bne 0x1000 <game_update>
    100c: b 0x10c0 <game_render>
00001080 <player_move>:
    1080: bx lr
000010c0 <game_render>:
    10c0: bl 0x1234 <unknown_external>
    10c4: bx lr
"""
ARM64 = """
0000000000401000 <scene_tick>:
  401000: 08 00 00 94 bl 0x401020 <physics_step>
  401004: blr x9
  401008: b.eq 0x401000 <scene_tick>
  40100c: b 0x401040 <render_frame>
0000000000401020 <physics_step>:
  401020: ret
0000000000401040 <render_frame>:
  401040: ret
"""


class CallgraphTests(unittest.TestCase):
    def test_arm32_direct_indirect_and_tail_calls(self):
        report = analyze_text(ARM32, "ARM32")
        self.assertEqual(report["function_count"], 3)
        self.assertEqual(len(report["calls"]), 3)
        self.assertEqual(len(report["indirect_calls"]), 1)
        self.assertEqual(report["calls"][0]["target_function"], "player_move")
        self.assertEqual(report["unresolved_direct_targets"], ["0x1234"])
        self.assertEqual(report["tail_edges"], [
            {"from": "game_update", "pc": "0x100c",
             "to": "game_render", "target": "0x10c0"}
        ])

    def test_arm64_raw_bytes_and_unresolved_indirect(self):
        report = analyze_text(ARM64, "ARM64")
        self.assertEqual(report["function_count"], 3)
        self.assertEqual(report["calls"][0]["target_function"], "physics_step")
        self.assertEqual(report["indirect_calls"][0]["opcode"], "blr")
        self.assertEqual(report["tail_edges"][0]["to"], "render_frame")
        self.assertEqual(report["unresolved_direct_targets"], [])

    def test_no_fake_functions_and_unsupported_arch(self):
        with self.assertRaisesRegex(ValueError, "no labeled functions"):
            analyze_text("  1000: bl 0x1010", "ARM32")
        with self.assertRaisesRegex(ValueError, "unsupported architecture"):
            analyze_text(ARM32, "x86_64")

    def test_elf_header_architecture_detection(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.elf"
            for cls, machine, expected in ((1, 40, "ARM32"), (2, 183, "ARM64")):
                header = bytearray(20)
                header[:6] = b"\x7fELF" + bytes([cls, 1])
                header[18:20] = machine.to_bytes(2, "little")
                p.write_bytes(header)
                self.assertEqual(elf_architecture(p), expected)
            p.write_bytes(b"not an ELF")
            with self.assertRaisesRegex(ValueError, "little-endian ELF"):
                elf_architecture(p)


if __name__ == "__main__":
    unittest.main()
