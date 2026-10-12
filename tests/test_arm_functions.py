"""Tests for ARM direct-call candidate discovery (synthetic ELF fixtures)."""
import importlib.util
from pathlib import Path
import struct
import unittest

path=Path(__file__).resolve().parents[1]/"tools"/"arm_functions.py"
spec=importlib.util.spec_from_file_location("arm_functions",path)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def elf(words):
    b=bytearray(0x100+4*len(words))
    b[:16]=b"\x7fELF"+bytes([1,1,1])+bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH",b,16,2,40,1,0x1000,52,0,0,52,32,1,0,0,0)
    struct.pack_into("<IIIIIIII",b,52,1,0x100,0x1000,0,4*len(words),4*len(words),5,4)
    for n,word in enumerate(words):
        struct.pack_into("<I",b,0x100+4*n,word)
    return bytes(b)

class CandidateTests(unittest.TestCase):
    def setUp(self):
        # BL from 0x1000 to 0x100c, BX LR at 0x1004 and 0x100c.
        self.data=elf([0xeb000001,0xe12fff1e,0xe1a00000,0xe12fff1e])
    def test_direct_call_creates_candidate(self):
        out=mod.discover(self.data,0x1000)
        self.assertEqual([f["address"] for f in out["candidates"]],["0x1000","0x100c"])
        self.assertEqual(out["calls"][0]["call_site"],"0x1000")
    def test_candidate_is_not_confirmed(self):
        out=mod.discover(self.data,0x1000)
        self.assertEqual(out["candidates"][1]["basis"],"direct_BL_target")
    def test_budget(self):
        with self.assertRaises(mod.cfg.arm.ScanError):
            mod.discover(self.data,0x1000,max_functions=1)
    def test_entry_outside_executable(self):
        with self.assertRaises(mod.cfg.arm.ScanError):
            mod.discover(self.data,0x2000)
    def test_no_call(self):
        out=mod.discover(elf([0xe12fff1e]),0x1000)
        self.assertEqual(out["candidate_count"],1)
        self.assertEqual(out["calls"],[])
if __name__=="__main__":
    unittest.main()
