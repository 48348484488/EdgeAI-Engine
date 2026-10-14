"""AArch64 indirect dispatch classifier: exact evidence, never resolves targets."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from aarch64_indirect_audit import analyze

SCAN = {
    "architecture": "AArch64", "function": "f", "entry": "0x1000",
    "size_bytes": 64, "sample_truncated": False,
    "control_transfer_candidates": [
        {"pc": "0x1010", "kind": "BR", "target": None},
        {"pc": "0x1020", "kind": "BLR", "target": None},
        {"pc": "0x1028", "kind": "BR", "target": None},
    ],
}
TEXT = """
    1004: adr x9, 0x1004
    1008: ldrsw x10, [x11, x8, lsl #2]
    100c: add x9, x9, x10
    1010: br x9
    101c: ldr x8, [x19, #0x78]
    1020: blr x8
    1024: nop
    1028: br x12
"""


class IndirectAuditTests(unittest.TestCase):
    def test_exact_pattern_and_unresolved_indirect(self):
        r=analyze(copy.deepcopy(SCAN),TEXT)
        self.assertEqual(r["indirect_site_count"],3)
        self.assertEqual(r["pattern_counts"]["pc_relative_indexed_table_dispatch_candidate"],1)
        self.assertEqual(r["pattern_counts"]["unclassified_indirect_branch"],1)
        self.assertEqual(r["pattern_counts"]["unresolved_indirect_call"],1)
        self.assertEqual(r["sites"][0]["evidence_pcs"],["0x1004","0x1008","0x100c","0x1010"])
        self.assertFalse(r["targets_resolved"])
        self.assertFalse(r["code_executed"])

    def test_reject_llvm_opcode_mismatch(self):
        with self.assertRaisesRegex(ValueError,"LLVM/scanner mismatch"):
            analyze(copy.deepcopy(SCAN), TEXT.replace("1010: br x9","1010: ret"))

    def test_nonconsecutive_sequence_not_classified(self):
        r=analyze(copy.deepcopy(SCAN),TEXT.replace("1008: ldrsw","1008: nop x10  // ldrsw"))
        self.assertEqual(r["sites"][0]["pattern"],"unclassified_indirect_branch")

    def test_refuse_truncated_scan(self):
        d=copy.deepcopy(SCAN)
        d["sample_truncated"]=True
        with self.assertRaisesRegex(ValueError,"complete"):
            analyze(d,TEXT)

    def test_declared_function_bounds(self):
        d=copy.deepcopy(SCAN)
        d["size_bytes"]=16
        with self.assertRaisesRegex(ValueError,"invalid indirect transfer"):
            analyze(d,TEXT)


if __name__ == "__main__":
    unittest.main()
