"""Regression tests: distinguish invalid positions, occupied cells and accepted plays."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

outcomes=load("tools/arm_play_outcomes.py","play_outcomes")
inspector=load("tools/inspect_tictactoe_memory.py","tic_inspector")
MAX=0xffffffff

def ins(pc,op,args):
    return {"pc":hex(pc),"mnemonic":op,"operands":args}

class PathOutcomeTests(unittest.TestCase):
    def test_three_distinct_outcomes(self):
        seq=[
            ins(0x1000,"cmp","r0, #8"),
            ins(0x1004,"bhi","0x101c"),
            ins(0x1008,"ldr","r3, [r2, r0, lsl #2]"),
            ins(0x100c,"cmp","r3, #0"),
            ins(0x1010,"beq","0x1024"),
            ins(0x1014,"mvn","r0, #0"),
            ins(0x1018,"bx","lr"),
            ins(0x101c,"mvn","r0, #0"),
            ins(0x1020,"bx","lr"),
            ins(0x1024,"str","r1, [r2, r0, lsl #2]"),
            ins(0x1028,"b","0x2000 <winner>")
        ]
        report=outcomes.analyze(seq,["0x1008"],["0x1024"])
        self.assertEqual({
            (x["event"],tuple(x["input_position_unsigned"]),x["board_cell"],x["board_written"])
            for x in report["outcomes"]
        },{
            ("return_minus_one",(9,MAX),"unknown",False),
            ("return_minus_one",(0,8),"occupied",False),
            ("winner_tail_jump",(0,8),"empty",True)
        })
        self.assertEqual(report["unsupported_pcs"],[])

    def test_no_unproven_board_read(self):
        seq=[
            ins(0x1000,"ldr","r3, [r2, r0, lsl #2]"),
            ins(0x1004,"cmp","r3, #0"),
            ins(0x1008,"beq","0x1010"),
            ins(0x100c,"bx","lr"),
            ins(0x1010,"bx","lr"),
        ]
        report=outcomes.analyze(seq,[],[])
        self.assertTrue(all(x["board_cell"]=="unknown" for x in report["outcomes"]))

    def test_actual_compiled_arm_game(self):
        report=inspector.evaluate()
        play=next(f for f in report["functions"] if f["name"]=="play")
        outcomes_list=play["path_outcomes"]["outcomes"]
        signatures={(x["event"],tuple(x["input_position_unsigned"]),x["board_cell"],x["board_written"]) for x in outcomes_list}
        self.assertEqual(signatures,{
            ("return_minus_one",(9,MAX),"unknown",False),
            ("return_minus_one",(0,8),"occupied",False),
            ("winner_tail_jump",(0,8),"empty",True)
        })
        self.assertEqual(play["path_outcomes"]["unsupported_pcs"],[])

if __name__=="__main__":unittest.main()
