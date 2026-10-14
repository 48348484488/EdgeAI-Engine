"""Conservative AArch64 argument-guard regression suite."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_arg_guards import infer
SCAN={"architecture":"AArch64","function":"UnityInitialize","entry":"0x1000",
      "size_bytes":40,"sample_truncated":False,"decoded_control_transfers":3,
      "control_transfer_candidates":[
          {"pc":"0x100c","kind":"BL","target":"0x2000"},
          {"pc":"0x1010","kind":"CBNZ","target":"0x2000"},
          {"pc":"0x101c","kind":"B.cond","target":"0x2000"}]}
CODE="\n".join((
 "1000: mov w21, w1","1004: mov x20, x0",
 "1008: add x0, x20, #0x8","100c: bl 0x2000",
 "1010: cbnz w0, 0x2000","1014: ldr x8, [x20]",
 "1018: cmp w21, #0x2e0","101c: b.ne 0x2000",
 "1020: ret","1024: nop"))+"\n"

class GuardTests(unittest.TestCase):
    def test_preserved_second_argument(self):
        r=infer(copy.deepcopy(SCAN),CODE)
        self.assertEqual(r["candidate_count"],1)
        g=r["candidates"][0]
        self.assertEqual((g["argument_index"],g["compared_immediate"],g["branch_if_argument"]),
                         (1,736,"not_equal"))
        self.assertEqual((g["copy_pc"],g["compare_pc"],g["conditional_branch_pc"]),
                         ("0x1000","0x1018","0x101c"))
        self.assertFalse(r["global_path_feasibility_proven"])
    def test_register_overwrite_rejected(self):
        r=infer(copy.deepcopy(SCAN),CODE.replace("1008: add x0, x20, #0x8","1008: add w21, w21, #1"))
        self.assertEqual(r["candidate_count"],0)
        self.assertEqual(r["rejected"][0]["reason"],"register_overwritten")
    def test_unknown_instruction_rejected(self):
        r=infer(copy.deepcopy(SCAN),CODE.replace("1008: add x0, x20, #0x8","1008: magicop x21, x0"))
        self.assertEqual(r["rejected"][0]["reason"],"unknown_register_effect")
    def test_branch_into_interval_rejected(self):
        scan=copy.deepcopy(SCAN)
        scan["control_transfer_candidates"].append({"pc":"0x1020","kind":"B","target":"0x1018"})
        scan["decoded_control_transfers"]=4
        r=infer(scan,CODE.replace("1020: ret","1020: b 0x1018"))
        self.assertEqual(r["candidate_count"],0)
        self.assertEqual(r["rejected"][0]["reason"],"branch_enters_tracked_interval")
    def test_truncated_scan_refused(self):
        scan=copy.deepcopy(SCAN);scan["sample_truncated"]=True
        with self.assertRaisesRegex(ValueError,"complete"):infer(scan,CODE)
    def test_wrong_branch_opcode_refused(self):
        scan=copy.deepcopy(SCAN);scan["control_transfer_candidates"][2]["kind"]="B"
        with self.assertRaisesRegex(ValueError,"disagree"):infer(scan,CODE)
    def test_register_width_mismatch_not_inferred(self):
        r=infer(copy.deepcopy(SCAN),CODE.replace("1018: cmp w21","1018: cmp x21"))
        self.assertEqual(r["candidate_count"],0)
    def test_unconditional_branch_breaks_linear_tracking(self):
        scan=copy.deepcopy(SCAN)
        scan["control_transfer_candidates"][1]={"pc":"0x1010","kind":"B","target":"0x2000"}
        r=infer(scan,CODE.replace("1010: cbnz w0, 0x2000","1010: b 0x2000"))
        self.assertEqual(r["rejected"][0]["reason"],"linear_control_flow_interrupted")
if __name__=="__main__":unittest.main()
