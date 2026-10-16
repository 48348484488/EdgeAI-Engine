"""Independent compiler-backed and rejection tests for EdgeAI AArch64 multistage lifters."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from aarch64_multimem_leaf_lifter import lift as lift_multimem, run as run_multimem
from aarch64_move_caller_lifter import lift as lift_caller, run as run_caller


class FailClosedTests(unittest.TestCase):
    def test_unrecognized_op_rejected(self):
        with self.assertRaisesRegex(ValueError,'unsupported opcode'):
            lift_multimem(0x1000,[(0x1000,'ldrsw','x1, [x0]'),(0x1004,'ret','')])

    def test_branch_outside_rejected(self):
        with self.assertRaisesRegex(ValueError,'branch outside'):
            lift_multimem(0x1000,[(0x1000,'ldr','w1, [x0]'),
                                  (0x1004,'str','w1, [x0]'),
                                  (0x1008,'b','0x4000'),(0x100c,'ret','')])

    def test_invalid_memory_scale_rejected(self):
        with self.assertRaisesRegex(ValueError,'unsupported index scale'):
            lift_multimem(0x1000,[(0x1000,'ldr','w1, [x0, x2, lsl #5]'),
                                  (0x1004,'str','w1, [x0]'),(0x1008,'ret','')])

    def test_incomplete_disassembly_rejected(self):
        with self.assertRaisesRegex(ValueError,'noncontiguous'):
            lift_multimem(0x1000,[(0x1000,'ldr','w1, [x0]'),(0x1008,'ret','')])

    def test_unbalanced_frame_rejected(self):
        rows=[(0x1000,'stp','x29, x30, [sp, #-0x20]!'),
              (0x1004,'mov','x29, sp'),
              (0x1008,'stp','x19, x20, [sp, #0x10]'),
              (0x100c,'mov','x19, x0'),
              (0x1010,'bl','0x2000'),
              (0x1014,'mov','x0, x19'),
              (0x1018,'ldp','x29, x30, [sp], #0x20'),
              (0x101c,'ret','')]
        with self.assertRaisesRegex(ValueError,'save/restore'):
            lift_caller(0x1000,rows,{0x2000:'board_only_mutator'})

    def test_unverified_bl_target_rejected(self):
        rows=[(0x1000,'stp','x29, x30, [sp, #-0x20]!'),
              (0x1004,'mov','x29, sp'),
              (0x1008,'stp','x19, x20, [sp, #0x10]'),
              (0x100c,'mov','x19, x0'),
              (0x1010,'bl','0x2000'),
              (0x1014,'ldp','x19, x20, [sp, #0x10]'),
              (0x1018,'ldp','x29, x30, [sp], #0x20'),
              (0x101c,'ret','')]
        with self.assertRaisesRegex(ValueError,'lacks tested ABI'):
            lift_caller(0x1000,rows,{})

    def test_missing_manifest_rejected(self):
        with self.assertRaisesRegex(ValueError,'ABI manifest'):
            run_caller(Path('/nonexistent.elf'),0x1000,{})


@unittest.skipUnless(all(shutil.which(x) for x in ('clang','ld.lld','llvm-objdump','g++')),
                     'Clang, LLD, LLVM disassembler and g++ required')
class CompilerBackedTests(unittest.TestCase):
    def test_stripped_arm64_elf_to_native_cpp_4096_arrays(self):
        asm="""
.text
.global _start
_start:
 bl update
 ret
update:
 ldr w3, [x0, x1, lsl #2]
 add w3, w3, #1
 str w3, [x0, x1, lsl #2]
 ldr w4, [x2]
 add w4, w4, #1
 str w4, [x2]
 mov w0, #1
 ret
"""
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'input.S').write_text(asm)
            subprocess.run(['clang','--target=aarch64-none-elf','-nostdlib',
                            '-fuse-ld=lld','-Wl,--strip-all','-Wl,-Ttext=0x1000',
                            '-Wl,-e,_start',str(p/'input.S'),'-o',str(p/'binary.elf')],
                           check=True,capture_output=True,text=True)
            cpp,report=run_multimem(p/'binary.elf',0x1008)
            self.assertEqual(report['instructions_translated'],8)
            self.assertFalse(report['symbols_used'])
            self.assertFalse(report['source_read'])
            (p/'candidate.cpp').write_text(cpp)
            subprocess.run(['g++','-std=c++17','-O2','-fPIC','-shared',
                            str(p/'candidate.cpp'),'-o',str(p/'candidate.so')],
                           check=True,capture_output=True,text=True)
            f=ctypes.CDLL(str(p/'candidate.so')).recovered_1008
            f.argtypes=(ctypes.POINTER(ctypes.c_uint32),
                        ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32))
            f.restype=ctypes.c_uint32
            for i in range(4096):
                expected=[(i*101+j*5)&0xffffffff for j in range(16)]
                board=(ctypes.c_uint32*16)(*expected)
                score=ctypes.c_uint32(i)
                col=i%4
                self.assertEqual(f(board,col,ctypes.byref(score)),1)
                expected[col]=(expected[col]+1)&0xffffffff
                self.assertEqual(list(board),expected)
                self.assertEqual(score.value,i+1)

    def test_synthetic_balanced_caller_cpp_1024_arrays(self):
        rows=[(0x1000,'stp','x29, x30, [sp, #-0x20]!'),
              (0x1004,'mov','x29, sp'),
              (0x1008,'stp','x19, x20, [sp, #0x10]'),
              (0x100c,'mov','x19, x0'),
              (0x1010,'bl','0x2000'),
              (0x1014,'mov','x0, x19'),
              (0x1018,'mov','w0, #1'),
              (0x101c,'ldp','x19, x20, [sp, #0x10]'),
              (0x1020,'ldp','x29, x30, [sp], #0x20'),
              (0x1024,'ret','')]
        cpp,_=lift_caller(0x1000,rows,{0x2000:'board_only_mutator'})
        cpp+='\nextern "C" void recovered_2000(uint32_t* board) { board[0] += 5; }\n'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'source.cpp').write_text(cpp)
            subprocess.run(['g++','-std=c++17','-O2','-fPIC','-shared',
                            str(p/'source.cpp'),'-o',str(p/'library.so')],
                           check=True,capture_output=True,text=True)
            f=ctypes.CDLL(str(p/'library.so')).recovered_1000
            f.argtypes=(ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_uint32))
            f.restype=ctypes.c_uint32
            for i in range(1024):
                board=(ctypes.c_uint32*16)(*([i]*16))
                score=ctypes.c_uint32(100)
                self.assertEqual(f(board,ctypes.byref(score)),1)
                self.assertEqual(board[0],i+5)
                self.assertEqual(score.value,100)


if __name__=='__main__':unittest.main()
