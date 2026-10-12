import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def load(path,name):
    sp=importlib.util.spec_from_file_location(name,ROOT/path)
    m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
paths=load("tools/arm_play_paths.py","play_paths")
game=load("tools/inspect_tictactoe_memory.py","game")
class Tests(unittest.TestCase):
    def test_rejection_and_write_paths(self):
        ins=[{"pc":hex(pc),"mnemonic":op,"operands":arg} for pc,op,arg in [
          (0x1000,"beq","0x1010"),(0x1004,"mvn","r0, #0"),
          (0x1008,"bx","lr"),(0x1010,"str","r1, [r2, r0, lsl #2]"),
          (0x1014,"b","0x2000 <winner>")]]
        report=paths.analyze(ins,["0x1010"])
        self.assertIn("sets_minus_one",report["forks"][0]["fallthrough"]["reachable_events"])
        self.assertIn("board_write",report["forks"][0]["taken"]["reachable_events"])
    def test_real_compiled(self):
        report=game.evaluate()
        play=next(x for x in report["functions"] if x["name"]=="play")
        self.assertTrue(play["path_events"]["forks"])
        combined=str(play["path_events"])
        self.assertIn("board_write",combined)
        self.assertIn("sets_minus_one",combined)
if __name__=="__main__":unittest.main()
