"""CFG branch and budget checks using synthetic ELF32 ARM fixtures."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec=importlib.util.spec_from_file_location("cfg",Path(__file__).resolve().parents[1]/"tools"/"arm_cfg.py")
cfg=importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)

def fixture(code):
    b=bytearray(0x100+len(code))
    b[:16]=b"\x7fELF"+bytes([1,1,1])+bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH",b,16,2,40,1,0x1000,52,0,0,52,32,1,0,0,0)
    struct.pack_into("<IIIIIIII",b,52,1,0x100,0x1000,0,len(code),len(code),5,4)
    b[0x100:]=code
    return b

class CFGTests(unittest.TestCase):
    def test_arm_branch_skips(self):
        r=cfg.build(fixture(struct.pack("<III",0xea000000,0xe1a00000,0xe12fff1e)),0x1000,"arm")
        self.assertEqual([n["address"] for n in r["instructions"]],["0x1000","0x1008"])
    def test_arm_call(self):
        r=cfg.build(fixture(struct.pack("<II",0xeb000000,0xe12fff1e)),0x1000,"arm")
        self.assertIn({"from":"0x1000","to":"0x1008","type":"call"},r["edges"])
        self.assertEqual(r["instruction_count"],2)
    def test_thumb_conditional(self):
        r=cfg.build(fixture(struct.pack("<HHH",0xd000,0x4770,0x4770)),0x1000,"thumb")
        self.assertEqual(r["instruction_count"],3)
    def test_thumb32_rejected(self):
        r=cfg.build(fixture(struct.pack("<HH",0xf000,0x8000)),0x1000,"thumb")
        self.assertEqual(r["instructions"][0]["kind"],"unsupported-thumb32")
        self.assertEqual(r["instruction_count"],1)
    def test_outside(self):
        with self.assertRaises(cfg.arm.ScanError):
            cfg.build(fixture(bytes(4)),0x2000,"arm")
    def test_budget(self):
        with self.assertRaises(cfg.arm.ScanError):
            cfg.build(fixture(struct.pack("<III",0xe1a00000,0xe1a00000,0xe12fff1e)),0x1000,"arm",1)

if __name__=="__main__": unittest.main()
