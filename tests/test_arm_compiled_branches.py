import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(p,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/p)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
branches=load("tools/arm_compiled_branches.py","branches")
game=load("tools/inspect_tictactoe_memory.py","game")

class BranchTests(unittest.TestCase):
    def test_branch_edges(self):
        ins=[{"pc":"0x1000","mnemonic":"cmp","operands":"r0, #8"},
             {"pc":"0x1004","mnemonic":"bhi","operands":"0x1010 <play+0x10>"},
             {"pc":"0x1008","mnemonic":"mov","operands":"r1, #5"},
             {"pc":"0x1010","mnemonic":"bx","operands":"lr"}]
        result=branches.analyze(ins)
        self.assertEqual(result["fork_count"],1)
        self.assertEqual(result["function_branch_forks"][0]["taken"],"0x1010")
    def test_real_compiled_play(self):
        report=game.evaluate()
        play=next(f for f in report["functions"] if f["name"]=="play")
        conditions={b["condition"] for b in play["control_flow"]["function_branch_forks"]}
        self.assertIn("eq",conditions)
        self.assertTrue(play["control_flow"]["fork_count"]>=1)
if __name__=="__main__":unittest.main()
