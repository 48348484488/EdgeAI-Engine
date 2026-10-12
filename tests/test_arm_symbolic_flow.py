import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/"tools"/"arm_symbolic_flow.py"
s=importlib.util.spec_from_file_location("symflow",p)
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)

def i(pc,mnemonic,operands):
    return {"pc":hex(pc),"mnemonic":mnemonic,"operands":operands}

class Tests(unittest.TestCase):
    def test_branch_preserves_board_base(self):
        ins=[i(0x1000,"movw","r2, #0x112c"),
             i(0x1004,"movt","r2, #0x2"),
             i(0x1008,"cmp","r0, #8"),
             i(0x100c,"bne","0x1014"),
             i(0x1010,"b","0x1014"),
             i(0x1014,"str","r1, [r2, r0, lsl #2]")]
        out=m.analyze(ins)
        self.assertEqual(out[0]["base_address"],"0x2112c")
        self.assertIsNone(out[0]["resolved_address"])
    def test_merge_different_bases_drops_value(self):
        ins=[i(0x1000,"cmp","r0, #0"),
             i(0x1004,"beq","0x1010"),
             i(0x1008,"mov","r2, #64"),
             i(0x100c,"b","0x1014"),
             i(0x1010,"mov","r2, #32"),
             i(0x1014,"ldr","r1, [r2]")]
        self.assertIsNone(m.analyze(ins)[0]["base_address"])
    def test_merge_same_base_keeps_value(self):
        ins=[i(0x1000,"mov","r2, #64"),
             i(0x1004,"beq","0x1010"),
             i(0x1008,"cmp","r0, #0"),
             i(0x100c,"b","0x1010"),
             i(0x1010,"ldr","r1, [r2]")]
        self.assertEqual(m.analyze(ins)[0]["resolved_address"],"0x40")
if __name__=="__main__":unittest.main()
