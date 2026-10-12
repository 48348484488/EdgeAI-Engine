import importlib.util
from pathlib import Path
import struct
import unittest

p=Path(__file__).resolve().parents[1]/"tools"/"arm_memory_flow.py"
spec=importlib.util.spec_from_file_location("memory_flow",p)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def sample(words):
    b=bytearray(0x100+4*len(words))
    b[:16]=bytes.fromhex("7f454c46010101")+bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH",b,16,2,40,1,0x1000,52,0,0,52,32,1,0,0,0)
    struct.pack_into("<IIIIIIII",b,52,1,0x100,0x1000,0,4*len(words),4*len(words),5,4)
    for i,w in enumerate(words):
        struct.pack_into("<I",b,0x100+4*i,w)
    return bytes(b)

class Tests(unittest.TestCase):
    def test_memory_survives_branch(self):
        data=sample([0xe3a01040,0xe3a00005,0xe5810004,0xea000000,0xe3a00009,0xe5912004,0xe12fff1e])
        out=m.analyze(data,0x1000)
        self.assertEqual(out["in_states"]["0x1018"]["registers"]["r2"],"0x5")
    def test_unknown_store_invalidates(self):
        data=sample([0xe3a01040,0xe3a00005,0xe5810000,0xe5830000,0xe5912000,0xe12fff1e])
        out=m.analyze(data,0x1000)
        self.assertNotIn("r2",out["in_states"]["0x1014"]["registers"])
    def test_unknown_instruction_stops(self):
        out=m.analyze(sample([0xe5d00000,0xe3a01001]),0x1000)
        self.assertIn("0x1000",out["unsupported_addresses"])
if __name__=="__main__":
    unittest.main()
