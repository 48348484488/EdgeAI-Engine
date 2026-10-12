import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/"tools"/"arm_play_evidence.py"
spec=importlib.util.spec_from_file_location("play_evidence",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def ins(pc,mnemonic,operands):
    return {"pc":hex(pc),"mnemonic":mnemonic,"operands":operands}

class Tests(unittest.TestCase):
    def test_comparison_and_branch(self):
        out=m.report([ins(0x1000,"cmp","r0, #9"),ins(0x1004,"bhs","0x1020")],0x2112c)
        self.assertEqual([x["kind"] for x in out["evidence"]],["comparison","branch"])
    def test_read_write_scaled_index(self):
        out=m.report([ins(0x1090,"ldr","r3, [r2, r0, lsl #2]"),
                      ins(0x10a4,"str","r1, [r2, r0, lsl #2]")],0x2112c)
        self.assertEqual([x["kind"] for x in out["evidence"]],["board_indexed_load","board_indexed_store"])
    def test_other_register_not_claimed(self):
        out=m.report([ins(0x1090,"ldr","r3, [r4, r0, lsl #2]")],0x2112c)
        self.assertEqual(out["evidence"],[])
if __name__=="__main__":unittest.main()
