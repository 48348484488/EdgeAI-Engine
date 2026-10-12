"""Teste de acessos ARM32 a memoria conhecida e desconhecida."""
import importlib.util
from pathlib import Path
import struct
import unittest

p=Path(__file__).resolve().parents[1]/"tools"/"arm_memory.py"
s=importlib.util.spec_from_file_location("edgeai_arm_memory",p)
mod=importlib.util.module_from_spec(s)
s.loader.exec_module(mod)

def elf(words):
    b=bytearray(0x100+4*len(words))
    b[:16]=b"\x7fELF"+bytes([1,1,1])+bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH",b,16,2,40,1,0x1000,52,0,0,52,32,1,0,0,0)
    struct.pack_into("<IIIIIIII",b,52,1,0x100,0x1000,0,4*len(words),4*len(words),5,4)
    for i,w in enumerate(words): struct.pack_into("<I",b,0x100+4*i,w)
    return bytes(b)

class MemoryTests(unittest.TestCase):
    def test_known_store_then_load(self):
        # mov r1,#64; mov r0,#5; str r0,[r1,#4]; ldr r2,[r1,#4]; bx lr
        d=elf([0xe3a01040,0xe3a00005,0xe5810004,0xe5912004,0xe12fff1e])
        result=mod.analyze(d,0x1000)
        self.assertEqual(result["known_registers"]["r2"],"0x5")
        self.assertEqual(result["known_writes"]["0x44"],"0x5")
    def test_unknown_memory_not_invented(self):
        result=mod.analyze(elf([0xe3a01040,0xe5912004,0xe12fff1e]),0x1000)
        self.assertNotIn("r2",result["known_registers"])
    def test_unknown_store_invalidates_memory(self):
        result=mod.analyze(elf([0xe3a01040,0xe3a00005,0xe5810004,0xe5830000,0xe5912004]),0x1000)
        self.assertNotIn("r2",result["known_registers"])
        self.assertEqual(result["known_writes"],{})
    def test_byte_instruction_not_supported(self):
        self.assertIsNone(mod.decode_memory(0xe5d12004))
    def test_stops_at_call(self):
        result=mod.analyze(elf([0xe3a01040,0xeb000000,0xe3a00005]),0x1000)
        self.assertNotIn("r0",result["known_registers"])
if __name__=="__main__":unittest.main()
