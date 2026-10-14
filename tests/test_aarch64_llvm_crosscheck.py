"""LLVM vs. EdgeAI AArch64 opcode AND direct branch target equality."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_llvm_crosscheck import compare, llvm_transfers

SCAN = {
    "architecture": "AArch64", "function": "UnitySendMessage", "entry": "0x1000",
    "size_bytes": 24, "sample_truncated": False, "decoded_control_transfers": 3,
    "control_transfer_candidates": [
        {"pc":"0x1000","kind":"CBZ","target":"0x1010"},
        {"pc":"0x1008","kind":"BL","target":"0x2000"},
        {"pc":"0x1014","kind":"RET","target":None},
    ],
}
GOOD="\n".join([
    " 1000: cbz w0, 0x1010",
    " 1004: mov w1, w2",
    " 1008: bl 0x2000 <symbol>",
    " 100c: add w0, w0, #0x1",
    " 1010: nop", " 1014: ret",
])+"\n"

class LLVMContractTests(unittest.TestCase):
    def test_correct_matches_all_three_including_two_targets(self):
        r=compare(SCAN,GOOD)
        self.assertEqual(r["status"],"MATCH")
        self.assertEqual(r["exact_agreements"],3)
        self.assertEqual(r["direct_target_agreements"],2)
        self.assertEqual(r["direct_target_comparisons"],2)
        self.assertFalse(r["original_code_executed"])

    def test_changed_opcode_fails(self):
        r=compare(SCAN,GOOD.replace("1008: bl","1008: b"))
        self.assertEqual(r["status"],"MISMATCH")
        self.assertEqual(r["total_mismatches"],1)

    def test_wrong_llvm_target_fails_even_if_opcode_matches(self):
        r=compare(SCAN,GOOD.replace("bl 0x2000","bl 0x3000"))
        self.assertEqual(r["status"],"MISMATCH")
        self.assertEqual(r["opcode_agreements"],3)
        self.assertEqual(r["exact_agreements"],2)
        self.assertEqual(r["direct_target_agreements"],1)

    def test_wrong_scanner_target_fails(self):
        s=copy.deepcopy(SCAN)
        s["control_transfer_candidates"][0]["target"]="0x1014"
        self.assertEqual(compare(s,GOOD)["total_mismatches"],1)

    def test_tbz_uses_last_hex_not_bit_index(self):
        llvm=" 1000: tbz w9, #0x3, 0x1050 <label>\n"
        self.assertEqual(llvm_transfers(llvm)[0x1000]["target"],0x1050)

    def test_b_cond_parses_direct_target(self):
        self.assertEqual(llvm_transfers(" 1004: b.ne 0x1ffc <other>\n")[0x1004],
                         {"kind":"B.cond","target":0x1ffc})

    def test_negative_branch_destination(self):
        self.assertEqual(llvm_transfers(" 1004: b 0xff0 <previous>\n")[0x1004]["target"],0xff0)

    def test_extra_llvm_branch_fails(self):
        self.assertEqual(compare(SCAN,GOOD.replace("100c: add","100c: b"))["status"],"MISMATCH")

    def test_missing_llvm_target_rejected(self):
        with self.assertRaisesRegex(ValueError,"omitted direct target"):
            compare(SCAN,GOOD.replace("1008: bl 0x2000 <symbol>","1008: bl target"))

    def test_truncated_scan_is_refused(self):
        s=copy.deepcopy(SCAN);s["sample_truncated"]=True
        with self.assertRaisesRegex(ValueError,"full"): compare(s,GOOD)

    def test_out_of_range_llvm_is_refused(self):
        with self.assertRaisesRegex(ValueError,"outside"):
            compare(SCAN,GOOD+"\n 1018: b 0x1000\n")

    def test_wrong_architecture_is_refused(self):
        s=copy.deepcopy(SCAN);s["architecture"]="ARM32"
        with self.assertRaisesRegex(ValueError,"AArch64"):compare(s,GOOD)

    def test_missing_scanner_direct_target_rejected(self):
        s=copy.deepcopy(SCAN);s["control_transfer_candidates"][0]["target"]=None
        with self.assertRaisesRegex(ValueError,"missing scanner"):
            compare(s,GOOD)

if __name__=="__main__": unittest.main()
