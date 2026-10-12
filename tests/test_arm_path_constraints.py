import importlib.util
from pathlib import Path
import unittest
p=Path(__file__).resolve().parents[1]/"tools"/"arm_path_constraints.py"
s=importlib.util.spec_from_file_location("path_constraints",p)
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)
def i(pc,op,args):
    return {"pc":hex(pc),"mnemonic":op,"operands":args}
class PathConstraintsTests(unittest.TestCase):
    def test_contradictory_branch_is_pruned(self):
        ins=[i(0x1000,"cmp","r0, #0"),i(0x1004,"beq","0x1010"),
             i(0x1008,"bx","lr"),i(0x1010,"cmp","r0, #1"),
             i(0x1014,"beq","0x1020"),i(0x1018,"bx","lr"),
             i(0x1020,"bx","lr")]
        result=m.explore(ins)
        self.assertEqual(result["pruned_contradictions"],1)
        self.assertEqual({x["pc"] for x in result["terminal_paths"]},{"0x1008","0x1018"})
    def test_register_write_invalidates_constraint(self):
        ins=[i(0x1000,"cmp","r0, #0"),i(0x1004,"beq","0x100c"),
             i(0x1008,"bx","lr"),i(0x100c,"mov","r0, #1"),
             i(0x1010,"cmp","r0, #1"),i(0x1014,"beq","0x1020"),
             i(0x1018,"bx","lr"),i(0x1020,"bx","lr")]
        result=m.explore(ins)
        self.assertEqual(result["pruned_contradictions"],0)
    def test_other_conditional_branch_preserves_both_edges(self):
        ins=[i(0x1000,"bhi","0x1008"),i(0x1004,"bx","lr"),
             i(0x1008,"bx","lr")]
        self.assertEqual(len(m.explore(ins)["terminal_paths"]),2)
if __name__=="__main__":unittest.main()
