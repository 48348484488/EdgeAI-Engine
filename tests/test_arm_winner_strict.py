"""Negative tests for independent ARM32 winner instruction and table recovery."""
import importlib.util
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('strict_winner',ROOT/'tools/reconstruct_winner.py')
recovery=importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.elf=Path(cls.tmp.name)/'game.elf'
        subprocess.run(['clang','--target=armv7-none-eabi','-marm','-O1',
                        '-fno-inline','-nostdlib','-fuse-ld=lld',
                        '-Wl,-Ttext=0x1000','-Wl,-e=start',
                        str(ROOT/'examples/reverse/tictactoe.c'),'-o',str(cls.elf)],
                        check=True,capture_output=True,text=True)
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
    def mutate(self,before,after):
        data=self.elf.read_bytes()
        self.assertEqual(data.count(before),1)
        changed=Path(self.tmp.name)/'mutated.elf'
        changed.write_bytes(data.replace(before,after,1))
        return changed
    def test_arm_loop_and_table_extraction(self):
        cpp,ev=recovery.reconstruct(self.elf)
        self.assertEqual(len(ev['rows']),8)
        self.assertEqual(ev['verified_instructions'],29)
        self.assertEqual(ev['loop_back_edge'],['0x1068','0x101c'])
        self.assertIn('{0, 1, 2}',cpp)
    def test_changed_xor_instruction_is_rejected(self):
        changed=self.mutate(struct.pack('<I',0xe0225004),struct.pack('<I',0xe0825004))
        with self.assertRaisesRegex(ValueError,'unsupported winner instruction'):
            recovery.reconstruct(changed)
    def test_out_of_bounds_table_byte_is_rejected(self):
        raw=bytes.fromhex('000102030405060708000306010407020508000408020406')
        changed=self.mutate(raw,bytes([9])+raw[1:])
        with self.assertRaisesRegex(ValueError,'invalid board index'):
            recovery.reconstruct(changed)
    def test_changed_valid_table_byte_changes_generated_cpp(self):
        raw=bytes.fromhex('000102030405060708000306010407020508000408020406')
        changed=self.mutate(raw,bytes([0,8,2])+raw[3:])
        cpp,ev=recovery.reconstruct(changed)
        self.assertEqual(ev['rows'][0],[0,8,2])
        self.assertIn('{0, 8, 2}',cpp)

if __name__=='__main__':
    unittest.main()
