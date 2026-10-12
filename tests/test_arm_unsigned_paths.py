import importlib.util
from pathlib import Path
import unittest
p=Path(__file__).resolve().parents[1]/"tools"/"arm_unsigned_paths.py"
s=importlib.util.spec_from_file_location("unsigned_paths",p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def i(pc,op,args):return {"pc":hex(pc),"mnemonic":op,"operands":args}
class Tests(unittest.TestCase):
    def test_limit(self):
        seq=[i(0x1000,"cmp","r0, #8"),i(0x1004,"bhi","0x1010"),
             i(0x1008,"bx","lr"),i(0x1010,"bx","lr")]
        o=m.explore(seq)
        self.assertEqual({tuple(v["unsigned_bounds"]["r0"]) for v in o["terminal_paths"]},{(0,8),(9,0xffffffff)})
    def test_impossible_path(self):
        seq=[i(0x1000,"cmp","r0, #8"),i(0x1004,"bhi","0x1010"),
             i(0x1008,"bx","lr"),i(0x1010,"cmp","r0, #8"),
             i(0x1014,"bls","0x1020"),i(0x1018,"bx","lr"),i(0x1020,"bx","lr")]
        self.assertEqual(m.explore(seq)["pruned_contradictions"],1)
    def test_register_write(self):
        seq=[i(0x1000,"cmp","r0, #8"),i(0x1004,"bhi","0x1010"),
             i(0x1008,"bx","lr"),i(0x1010,"mov","r0, #0"),i(0x1014,"bx","lr")]
        o=m.explore(seq)
        self.assertEqual(next(x for x in o["terminal_paths"] if x["pc"]=="0x1014")["unsigned_bounds"],{})
if __name__=="__main__":unittest.main()
