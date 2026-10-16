"""Lifter regressions: exact lowered opcodes and fail-closed unknown instructions."""
from pathlib import Path
import ctypes
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from aarch64_leaf_lifter import lift, run


class LeafLifterTests(unittest.TestCase):
    def test_disallowed_opcode_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsupported opcode'):
            lift(0x1000,[(0x1000,'bl','0x1100'),(0x1004,'ret','')])

    def test_branch_to_unknown_destination_rejected(self):
        with self.assertRaisesRegex(ValueError, 'branch out'):
            lift(0x1000,[(0x1000,'b','0x100c'),(0x1004,'ret','')])

    def test_memory_write_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsupported opcode'):
            lift(0x1000,[(0x1000,'str','w0, [x1]'),(0x1004,'ret','')])

    def test_pointer_buffer_contract_enforced(self):
        with self.assertRaisesRegex(ValueError, 'memory contract'):
            lift(0x1000,[(0x1000,'ldr','w0, [x0]'),(0x1004,'ret','')],mem_size=0)

    @unittest.skipUnless(shutil.which('clang') and shutil.which('ld.lld') and
                         shutil.which('g++') and shutil.which('llvm-objdump'),
                         'compiler chain unavailable')
    def test_real_aarch64_assembly_lift_and_native_differential(self):
        asm='''
.text
.global _start
_start:
 bl toy
 ret
toy:
 mov x1, #0
loop:
 ldr w2, [x0, x1, lsl #2]
 cbz w2, zero
 add x1, x1, #1
 cmp x1, #4
 b.ne loop
 mov w0, #0
 ret
zero:
 mov w0, #1
 ret
'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'input.S').write_text(asm)
            subprocess.run(['clang','--target=aarch64-none-elf','-nostdlib',
                            '-fuse-ld=lld', '-Wl,--strip-all','-Wl,-Ttext=0x1000',
                            '-Wl,-e,_start',str(p/'input.S'),'-o',str(p/'input.elf')],
                           capture_output=True,check=True)
            source, report=run(p/'input.elf',0x1008,mem_size=16)
            self.assertTrue(report['all_instructions_covered'])
            self.assertEqual(report['instructions_translated'],10)
            self.assertFalse(report['symbols_used'])
            self.assertFalse(report['source_read'])
            (p/'generated.cpp').write_text(source)
            subprocess.run(['g++','-std=c++17','-O2','-fPIC','-shared',
                            str(p/'generated.cpp'),'-o',str(p/'generated.so')],
                           capture_output=True,check=True)
            dylib=ctypes.CDLL(str(p/'generated.so'))
            f=dylib.recovered_1008
            f.restype=ctypes.c_int32
            f.argtypes=[ctypes.POINTER(ctypes.c_uint32)]
            for x in range(256):
                values=[(x>>i)&1 for i in range(4)]
                a=(ctypes.c_uint32*4)(*values)
                self.assertEqual(f(a),int(any(not v for v in values)))


if __name__=='__main__':
    unittest.main()
