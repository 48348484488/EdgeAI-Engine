"""ARM32 control-flow constant propagation regressions."""
import importlib.util
from pathlib import Path
import struct
import unittest

p=Path(__file__).resolve().parents[1]/"tools"/"arm_dataflow.py"
s=importlib.util.spec_from_file_location("edgeai_dataflow",p)
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)

def elf(words):
    b=bytearray(0x100+4*len(words))
    b[:16]=b"\x7fELF"+bytes([1,1,1])+bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH",b,16,2,40,1,0x1000,52,0,0,52,32,1,0,0,0)
    struct.pack_into("<IIIIIIII",b,52,1,0x100,0x1000,0,4*len(words),4*len(words),5,4)
    for i,w in enumerate(words): struct.pack_into("<I",b,0x100+i*4,w)
    return bytes(b)

class FlowTests(unittest.TestCase):
    def test_known_comparison_prunes_branch(self):
        # mov r0,#5; cmp r0,#5; beq 0x1010; mov r1,#9; bx lr
        out=m.analyze(elf([0xe3a00005,0xe3500005,0x0a000000,0xe3a01009,0xe12fff1e]),0x1000)
        self.assertNotIn("0x100c",out["in_states"])
        self.assertIn("0x1010",out["in_states"])
    def test_unknown_comparison_keeps_both_paths(self):
        out=m.analyze(elf([0xe3500005,0x0a000000,0xe3a01009,0xe12fff1e]),0x1000)
        self.assertIn("0x1008",out["in_states"])
        self.assertIn("0x100c",out["in_states"])
    def test_join_discards_conflicting_constant(self):
        # cmp unknown r0; beq 0x1010; mov r1,#1; b 0x1014; mov r1,#2; bx lr
        out=m.analyze(elf([0xe3500005,0x0a000001,0xe3a01001,0xea000000,0xe3a01002,0xe12fff1e]),0x1000)
        self.assertNotIn("r1",out["in_states"]["0x1014"])
    def test_join_preserves_equal_constant(self):
        out=m.analyze(elf([0xe3500005,0x0a000001,0xe3a01001,0xea000000,0xe3a01001,0xe12fff1e]),0x1000)
        self.assertEqual(out["in_states"]["0x1014"]["r1"],"0x1")
    def test_unsupported_stops(self):
        out=m.analyze(elf([0xe5900000,0xe3a01001]),0x1000)
        self.assertIn("0x1000",out["unsupported_addresses"])
        self.assertNotIn("0x1004",out["in_states"])
if __name__=="__main__":unittest.main()
