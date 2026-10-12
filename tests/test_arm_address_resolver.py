"""Ensure indexed address calculation never guesses unknown registers."""
import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/"tools"/"arm_address_resolver.py"
spec=importlib.util.spec_from_file_location("arm_address_resolver",p)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ResolverTests(unittest.TestCase):
    def test_imm(self):
        self.assertEqual(module.resolve("r0, [r1, #12]",{"r1":0x2000}),0x200c)
    def test_indexed_scaled(self):
        self.assertEqual(module.resolve("r2, [r1, r3, lsl #2]",{"r1":0x2000,"r3":4}),0x2010)
    def test_unresolved(self):
        self.assertIsNone(module.resolve("r0, [r1, r3, lsl #2]",{"r1":0x2000}))
    def test_linear_known_addresses(self):
        instructions=[{"pc":"0x1000","mnemonic":"mov","operands":"r1, #64"},
                      {"pc":"0x1004","mnemonic":"mov","operands":"r3, #2"},
                      {"pc":"0x1008","mnemonic":"str","operands":"r0, [r1, r3, lsl #2]"}]
        self.assertEqual(module.walk(instructions)[0]["resolved_address"],"0x48")
    def test_unknown_opcode_invalidates(self):
        instructions=[{"pc":"0x1000","mnemonic":"mov","operands":"r1, #64"},
                      {"pc":"0x1004","mnemonic":"unknown","operands":""},
                      {"pc":"0x1008","mnemonic":"str","operands":"r0, [r1]"}]
        self.assertIsNone(module.walk(instructions)[0]["resolved_address"])
if __name__=="__main__":unittest.main()
