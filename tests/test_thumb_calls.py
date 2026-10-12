"""Thumb-2 direct BL/BLX call edge and mixed-mode candidate regressions."""
import importlib.util
from pathlib import Path
import struct
import unittest

root=Path(__file__).resolve().parents[1]/"tools"
spec=importlib.util.spec_from_file_location("edgeai_functions",root/"arm_functions.py")
fn=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fn)

def image(thumb_words, arm_words=()):
    b=bytearray(0x200)
    b[:16]=b"\x7fELF"+bytes([1,1,1])+bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH",b,16,2,40,1,0x1000,52,0,0,52,32,1,0,0,0)
    struct.pack_into("<IIIIIIII",b,52,1,0x100,0x1000,0,0x100,0x100,5,4)
    for i,v in enumerate(thumb_words):
        struct.pack_into("<H",b,0x100+2*i,v)
    for i,v in enumerate(arm_words):
        struct.pack_into("<I",b,0x100+0x20+4*i,v)
    return bytes(b)

class ThumbCallTests(unittest.TestCase):
    def test_bl_thumb(self):
        # BL +0: F000 F800, target is PC+4, return to PC+4
        d=image([0xf000,0xf800,0x4770])
        g=fn.cfg.build(d,0x1000,"thumb")
        self.assertEqual(g["instructions"][0]["width"],4)
        self.assertIn({"from":"0x1000","to":"0x1004","type":"call:thumb"},g["edges"])
        self.assertEqual(g["instruction_count"],2)
    def test_blx_arm(self):
        # BLX +0: F000 E800, ARM destination 0x1004
        d=image([0xf000,0xe800,0x4770])
        g=fn.cfg.build(d,0x1000,"thumb")
        self.assertIn({"from":"0x1000","to":"0x1004","type":"call:arm"},g["edges"])
    def test_mixed_mode_candidates(self):
        # BLX to ARM code at aligned 0x1004; ARM returns via BX LR.
        d=image([0xf000,0xe800,0x4770,0],[])
        b=bytearray(d)
        struct.pack_into("<I",b,0x104,0xe12fff1e)
        out=fn.discover(bytes(b),0x1000,"thumb")
        self.assertEqual(out["candidate_count"],2)
        self.assertEqual(out["calls"][0]["target_mode"],"arm")
    def test_negative_bl(self):
        # BL -4: F7FF FFFE -> target 0x1000.
        d=image([0xf7ff,0xfffe,0x4770])
        g=fn.cfg.build(d,0x1000,"thumb")
        self.assertIn({"from":"0x1000","to":"0x1000","type":"call:thumb"},g["edges"])
    def test_unsupported_thumb32_no_false_tail(self):
        d=image([0xf000,0x8000,0x4770])
        g=fn.cfg.build(d,0x1000,"thumb")
        self.assertEqual(g["instruction_count"],1)
        self.assertEqual(g["instructions"][0]["kind"],"unsupported-thumb32")

if __name__=="__main__":
    unittest.main()
