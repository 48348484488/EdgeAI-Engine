"""Synthetic ELF compiler-backed regressions for ARM64 scalar and linked lifters."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'tools'))
from aarch64_scalar_lifter import lift_scalar,run as scalar_run
from aarch64_linked_lifter import lift_linked


class ScalarTests(unittest.TestCase):
    def test_non_reg_scalar_rejected(self):
        with self.assertRaisesRegex(ValueError,'unsupported scalar opcode'):
            lift_scalar(0x1000,[(0x1000,'adrp','x0, 0x4000'),(0x1004,'ret','')])

    def test_out_of_function_branch_rejected(self):
        with self.assertRaisesRegex(ValueError,'branch outside'):
            lift_scalar(0x1000,[(0x1000,'cmp','w0, #1'),(0x1004,'b.eq','0x2000'),(0x1008,'ret','')])

    def test_requires_conditional_structure(self):
        with self.assertRaisesRegex(ValueError,'no return or compare'):
            lift_scalar(0x1000,[(0x1000,'mov','w0, #5'),(0x1004,'ret','')])

    @unittest.skipUnless(all(shutil.which(x) for x in ('clang','ld.lld','llvm-objdump','g++')),
                         'Clang/LLVM native toolchain unavailable')
    def test_stripped_elf_scalar_lift_and_4096_native_checks(self):
        asm='''
.text
.global _start
_start:
 bl value_to_class
 ret
value_to_class:
 mov w1, #8
 cmp w0, #8
 mov w2, #2
 csel w0, w1, w2, eq
 ret
'''
        with tempfile.TemporaryDirectory() as temp:
            d=Path(temp)
            (d/'source.S').write_text(asm)
            subprocess.run(['clang','--target=aarch64-none-elf','-nostdlib','-fuse-ld=lld',
                            '-Wl,--strip-all','-Wl,-Ttext=0x1000','-Wl,-e,_start',
                            str(d/'source.S'),'-o',str(d/'target.elf')],
                           check=True,capture_output=True)
            code,meta=scalar_run(d/'target.elf',0x1008)
            self.assertFalse(meta['source_read'])
            self.assertFalse(meta['symbols_used'])
            self.assertEqual(meta['instruction_count'],5)
            (d/'reconstructed.cpp').write_text(code)
            subprocess.run(['g++','-std=c++17','-O2','-shared','-fPIC',
                            str(d/'reconstructed.cpp'),'-o',str(d/'reconstructed.so')],
                           check=True,capture_output=True)
            f=ctypes.CDLL(str(d/'reconstructed.so')).recovered_1008
            f.argtypes=[ctypes.c_uint32];f.restype=ctypes.c_uint32
            for i in range(4096):
                self.assertEqual(f(i),8 if i==8 else 2)


class LinkedCallerTests(unittest.TestCase):
    def test_frame_required(self):
        with self.assertRaisesRegex(ValueError,'unrecognized paired-register'):
            lift_linked(0x1000,[(0x1000,'mov','x19, x0'),
                                (0x1004,'mov','x0, x19'),
                                (0x1008,'bl','0x2000'),
                                (0x100c,'ret',''),
                                (0x1010,'nop',''),
                                (0x1014,'ret','')],{0x2000:'read_only_leaf'})

    def test_unknown_call_not_silently_stubbed(self):
        rows=[(0x1000,'stp','x29, x30, [sp, #-0x20]!'),
              (0x1004,'mov','x29, sp'),
              (0x1008,'stp','x19, x20, [sp, #0x10]'),
              (0x100c,'bl','0x2000'),
              (0x1010,'ldp','x19, x20, [sp, #0x10]'),
              (0x1014,'ldp','x29, x30, [sp], #0x20'),
              (0x1018,'ret','')]
        with self.assertRaisesRegex(ValueError,'BL callee not in previously lifted'):
            lift_linked(0x1000,rows,{})


if __name__=='__main__':unittest.main()
