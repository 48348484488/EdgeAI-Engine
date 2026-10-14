"""LLVM vs. EdgeAI AArch64 control transfer equality and negative cases."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_llvm_crosscheck import compare

SCAN={"architecture":"AArch64","function":"UnitySendMessage","entry":"0x1000",
      "size_bytes":24,"sample_truncated":False,"decoded_control_transfers":3,
      "control_transfer_candidates":[
          {"pc":"0x1000","kind":"CBZ","target":"0x1010"},
          {"pc":"0x1008","kind":"BL","target":"0x2000"},
          {"pc":"0x1014","kind":"RET","target":None}
      ]}
GOOD="\n".join([" 1000: cbz w0, 0x1010"," 1004: mov w1, w2",
                 " 1008: bl 0x2000"," 100c: add w0, w0, #0x1",
                 " 1010: nop", " 1014: ret"])+"\n"

class LLVMContractTests(unittest.TestCase):
    def test_correct_matches_all_three(self):
        report=compare(SCAN,GOOD)
        self.assertEqual(report["status"],"MATCH")
        self.assertEqual(report["exact_agreements"],3)
        self.assertFalse(report["original_code_executed"])

    def test_changed_opcode_fails(self):
        report=compare(SCAN,GOOD.replace("1008: bl","1008: b"))
        self.assertEqual(report["status"],"MISMATCH")
        self.assertEqual(report["total_mismatches"],1)

    def test_extra_llvm_branch_fails(self):
        report=compare(SCAN,GOOD.replace("100c: add","100c: b"))
        self.assertEqual(report["status"],"MISMATCH")

    def test_truncated_scan_is_refused(self):
        scan=copy.deepcopy(SCAN)
        scan["sample_truncated"]=True
        with self.assertRaisesRegex(ValueError,"full"):
            compare(scan,GOOD)

    def test_out_of_range_llvm_is_refused(self):
        with self.assertRaisesRegex(ValueError,"outside"):
            compare(SCAN,GOOD+"\n 1018: b 0x1000\n")

    def test_wrong_architecture_is_refused(self):
        scan=copy.deepcopy(SCAN)
        scan["architecture"]="ARM32"
        with self.assertRaisesRegex(ValueError,"AArch64"):
            compare(scan,GOOD)

if __name__=="__main__":unittest.main()
