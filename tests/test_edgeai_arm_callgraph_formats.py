"""Regression: LLVM objdump ARM/Thumb raw formats preserve call edges."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgeai_arm_callgraph import analyze_text


class ArmCallgraphFormats(unittest.TestCase):
    def test_thumb_separate_bytes_and_halfwords(self):
        disassembly = """
00001000 <entry>:
  1000: 00 f0 00 f8 bl 0x2000 <worker>
  1004: f000 f800 bl 0x2000 <worker>
  1008: 00 47 blx r0
  100a: e000 b.w 0x2000 <worker>
00002000 <worker>:
  2000: 70 47 bx lr
"""
        graph = analyze_text(disassembly, "ARM32")
        self.assertEqual(graph["function_count"], 2)
        self.assertEqual(len(graph["calls"]), 3)
        self.assertEqual([c["indirect"] for c in graph["calls"]], [False, False, True])
        self.assertEqual(graph["calls"][0]["target_function"], "worker")
        self.assertEqual(len(graph["tail_edges"]), 1)

    def test_thumb_interworking_bit_normalized_for_label_lookup(self):
        disassembly = """
00001000 <entry>:
  1000: blx 0x2001 <worker>
00002000 <worker>:
  2000: bx lr
"""
        graph = analyze_text(disassembly, "ARM32")
        self.assertEqual(graph["calls"][0]["target"], "0x2001")
        self.assertEqual(graph["calls"][0]["target_function"], "worker")
        self.assertEqual(graph["unresolved_direct_targets"], [])

    def test_arm32_word_and_no_raw(self):
        disassembly = """
00001000 <entry>:
  1000: eb000001 bl 0x2000 <worker>
  1004: bl 0x2000 <worker>
00002000 <worker>:
  2000: e12fff1e bx lr
"""
        graph = analyze_text(disassembly, "ARM32")
        self.assertEqual(len(graph["calls"]), 2)
        self.assertEqual(graph["functions"][0]["instruction_count"], 2)
        self.assertEqual(graph["unresolved_direct_targets"], [])

    def test_aarch64_raw_and_indirect(self):
        disassembly = """
00001000 <entry>:
  1000: 94000001 bl 0x3000 <target>
  1004: d63f0120 blr x9
  1008: 14000001 b 0x3000 <target>
00003000 <target>:
  3000: d65f03c0 ret
"""
        graph = analyze_text(disassembly, "ARM64")
        self.assertEqual(len(graph["calls"]), 2)
        self.assertEqual(len(graph["indirect_calls"]), 1)
        self.assertEqual(graph["calls"][0]["target_function"], "target")
        self.assertEqual(len(graph["tail_edges"]), 1)

    def test_stripped_section_label_is_not_a_proven_function(self):
        disassembly = """
00001000 <.text>:
  1000: bl 0x2000
  1004: blr x8
00002000 <known_export>:
  2000: ret
"""
        graph = analyze_text(disassembly, "ARM64")
        self.assertEqual(graph["section_pseudolabel_count"], 1)
        self.assertEqual(graph["disassembled_instruction_count"], 3)
        self.assertEqual(graph["unresolved_direct_call_count"], 0)
        self.assertEqual(len(graph["indirect_calls"]), 1)

    def test_indirect_branch_sites_are_not_guessed_tail_calls(self):
        arm64 = """
00001000 <dispatch>:
  1000: blraa x17, x16
  1004: br x9
  1008: braa x10, x11
  100c: br x30
  1010: ret
"""
        graph = analyze_text(arm64, "ARM64")
        self.assertEqual(len(graph["calls"]), 1)
        self.assertTrue(graph["calls"][0]["indirect"])
        self.assertEqual(graph["calls"][0]["opcode"], "blraa")
        self.assertEqual(graph["unresolved_indirect_branch_count"], 2)
        self.assertEqual([x["opcode"] for x in graph["indirect_branches"]], ["br", "braa"])
        self.assertEqual(graph["tail_edges"], [])

        arm32 = """
00002000 <dispatch>:
  2000: bx r2
  2004: bx lr
  2008: bx r14
"""
        graph = analyze_text(arm32, "ARM32")
        self.assertEqual(graph["unresolved_indirect_branch_count"], 1)
        self.assertEqual(graph["indirect_branches"][0]["operands"], "r2")

    def test_gnu_style_thumb_wide_calls_and_branch_immediates(self):
        disassembly = """
00001000 <entry>:
  1000: bl.w #0x2001 <worker>
  1004: blx.w 2001 <worker>
  1008: b.w #0x2000 <worker>
  100c: blx r3
00002000 <worker>:
  2000: bx lr
"""
        graph = analyze_text(disassembly, "ARM32")
        self.assertEqual([c["opcode"] for c in graph["calls"]],
                         ["bl.w", "blx.w", "blx"])
        self.assertEqual([c["target_function"] for c in graph["calls"]],
                         ["worker", "worker", None])
        self.assertEqual([c["indirect"] for c in graph["calls"]],
                         [False, False, True])
        self.assertEqual(len(graph["tail_edges"]), 1)
        self.assertEqual(graph["tail_edges"][0]["to"], "worker")
        self.assertEqual(graph["unresolved_direct_targets"], [])

    def test_bare_hex_arm64_branch_and_register_indirect(self):
        disassembly = """
00001000 <entry>:
  1000: bl 2000 <worker>
  1004: blr x9
  1008: b #0x2000 <worker>
00002000 <worker>:
  2000: ret
"""
        graph = analyze_text(disassembly, "ARM64")
        self.assertEqual(graph["calls"][0]["target_function"], "worker")
        self.assertEqual(graph["calls"][1]["target"], None)
        self.assertEqual(len(graph["tail_edges"]), 1)

    def test_reject_unsupported_architecture(self):
        with self.assertRaises(ValueError):
            analyze_text("1000 <entry>:\\n 1000: bl 0x2000", "x86")


if __name__ == "__main__":
    unittest.main()
