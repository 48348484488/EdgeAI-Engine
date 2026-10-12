"""Tests for cross-entry unconditional branches and outline safeguards."""
import importlib.util
from pathlib import Path
import struct
import unittest
p=Path(__file__).resolve().parents[1]/"tools"/"arm_flow_outline.py"
s=importlib.util.spec_from_file_location("arm_flow_outline",p)
m=importlib.util.module_from_spec(s)
s.loader.exec_module(m)

def elf(words):
    b=bytearray(0x100+len(words)*4)
    b[:16]=b"\x7fELF"+bytes([1,1,1])+bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH",b,16,2,40,1,0x1000,52,0,0,52,32,1,0,0,0)
    struct.pack_into("<IIIIIIII",b,52,1,0x100,0x1000,0,4*len(words),4*len(words),5,4)
    for i,x in enumerate(words): struct.pack_into("<I",b,0x100+i*4,x)
    return bytes(b)

class OutlineTests(unittest.TestCase):
    def test_tail_between_known_entries(self):
        # 0x1000: B 0x1008; 0x1008: BX LR
        out=m.analyze(elf([0xea000000,0xe12fff1e,0xe12fff1e]),[0x1000,0x1008])
        self.assertEqual(out["functions"][0]["possible_tail_transfers"][0]["target"],"0x1008")
        self.assertIn("comportamento não reconstruído",out["functions"][0]["pseudocode_outline"])
    def test_no_target_without_independent_entry(self):
        out=m.analyze(elf([0xea000000,0xe12fff1e,0xe12fff1e]),[0x1000])
        self.assertEqual(out["functions"][0]["possible_tail_transfers"],[])
    def test_empty_entries(self):
        with self.assertRaises(m.cfg.arm.ScanError):
            m.analyze(elf([0xe12fff1e]),[])
if __name__=="__main__": unittest.main()
