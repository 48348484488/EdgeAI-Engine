"""Regression tests for the read-only ELF symbol inspector."""
import importlib.util
from pathlib import Path
import struct
import unittest

path = Path(__file__).resolve().parents[1] / "tools" / "elf_inspect.py"
spec = importlib.util.spec_from_file_location("edgeai_elf_inspect", path)
elf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(elf)

def fixture():
    data = bytearray(0x240)
    data[:16] = b"\x7fELF" + bytes([2,1,1]) + bytes(9)
    struct.pack_into("<HHIQQQIHHHHHH",data,16,2,62,1,0x401000,0,0x100,0,64,0,0,64,3,0)
    struct.pack_into("<IIQQQQIIQQ",data,0x100+64,0,3,0,0,0x200,13,0,0,1,0)
    struct.pack_into("<IIQQQQIIQQ",data,0x100+128,0,2,0,0,0x210,48,1,0,8,24)
    data[0x200:0x20d] = b"\x00player_jump\x00"
    struct.pack_into("<IBBHQQ",data,0x210+24,1,0x12,0,1,0x401200,48)
    return bytes(data)

class ELFInspectTest(unittest.TestCase):
    def test_named_function(self):
        result = elf.inspect(fixture())
        self.assertEqual(result["function_count"],1)
        self.assertEqual(result["functions"][0]["name"],"player_jump")
        self.assertEqual(result["functions"][0]["address"],"0x401200")
        self.assertEqual(result["functions"][0]["size"],48)
    def test_no_sections(self):
        data = bytearray(fixture())
        struct.pack_into("<Q",data,40,0)
        struct.pack_into("<H",data,60,0)
        self.assertEqual(elf.inspect(data)["function_count"],0)
    def test_bad_magic(self):
        with self.assertRaises(elf.ELFError):
            elf.inspect(b"not an ELF")
    def test_truncated(self):
        with self.assertRaises(elf.ELFError):
            elf.inspect(fixture()[:0x125])
    def test_invalid_symbol_name(self):
        data = bytearray(fixture())
        struct.pack_into("<I",data,0x210+24,99)
        with self.assertRaises(elf.ELFError):
            elf.inspect(data)

if __name__ == "__main__":
    unittest.main()
