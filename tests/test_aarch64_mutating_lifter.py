"""Negative and compiler-backed tests of source-blind ARM64 array mutator lifter."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from aarch64_mutating_lifter import _memory_access, lift_mutator, run


class MemoryEffectsTests(unittest.TestCase):
    def test_preindex_load_updates_register_only_after_access(self):
        code = _memory_access('str', 'w4, [x2, #0x10]!', 64)
        self.assertIn('std::memcpy(reinterpret_cast<void*>', code)
        self.assertIn('r[2] = uint64_t(addr);', code)

    def test_memory_bounds_are_explicit(self):
        code = _memory_access('ldr', 'w5, [x3, x1, lsl #2]', 64)
        self.assertIn('addr < origin', code)
        self.assertIn('addr-origin > 60ULL', code)
        self.assertIn('uint32_t word=0', code)

    def test_reject_unknown_store_destination(self):
        with self.assertRaisesRegex(ValueError, 'unsupported memory operand'):
            _memory_access('str', 'q0, [x1]', 64)

    def test_reject_unsupported_unscaled_memory(self):
        with self.assertRaisesRegex(ValueError, 'unsupported register offset scaling'):
            _memory_access('str', 'w0, [x1, x2, lsl #5]', 64)

    def test_reject_unrecognized_branch(self):
        with self.assertRaisesRegex(ValueError, 'branch outside'):
            lift_mutator(0x1000, [(0x1000,'ldr','w1, [x0]'),
                                  (0x1004,'str','w1, [x0]'),
                                  (0x1008,'b','0x5000'),
                                  (0x100c,'ret','')])

    def test_reject_non_memory_mutator(self):
        with self.assertRaisesRegex(ValueError, 'need read, write and return'):
            lift_mutator(0x1000, [(0x1000,'ldr','w1, [x0]'),
                                  (0x1004,'ret','')])

    def test_reject_call_opcode(self):
        with self.assertRaisesRegex(ValueError, 'unsupported ARM64 opcode'):
            lift_mutator(0x1000, [(0x1000,'ldr','w1, [x0]'),
                                  (0x1004,'bl','0x3000'),
                                  (0x1008,'str','w1, [x0]'),
                                  (0x100c,'ret','')])

    @unittest.skipUnless(all(shutil.which(x) for x in ('clang','ld.lld','llvm-objdump','g++')),
                         'requires Clang/LLD/LLVM C++ toolchains')
    def test_compiled_stripped_arm64_mutator_with_8000_arrays(self):
        asm='''
.text
.global _start
_start:
    bl rotate_2
    ret
rotate_2:
    ldr w1, [x0]
    ldr w2, [x0, #4]
    str w1, [x0, #4]
    str w2, [x0]
    ret
'''
        with tempfile.TemporaryDirectory() as td:
            d=Path(td)
            (d/'input.S').write_text(asm)
            subprocess.run(['clang','--target=aarch64-none-elf','-nostdlib',
                            '-fuse-ld=lld','-Wl,--strip-all','-Wl,-Ttext=0x1000',
                            '-Wl,-e,_start',str(d/'input.S'),'-o',str(d/'tiny.elf')],
                           capture_output=True,text=True,check=True)
            cpp, report=run(d/'tiny.elf',0x1008,mem_size=8)
            self.assertEqual(report['instruction_count'],5)
            self.assertFalse(report['symbols_used'])
            self.assertFalse(report['source_read'])
            (d/'candidate.cpp').write_text(cpp)
            subprocess.run(['g++','-std=c++17','-O2','-fPIC','-shared',
                            str(d/'candidate.cpp'),'-o',str(d/'candidate.so')],
                           capture_output=True,text=True,check=True)
            lib=ctypes.CDLL(str(d/'candidate.so'))
            fn=lib.recovered_1008
            fn.argtypes=[ctypes.POINTER(ctypes.c_uint32)]
            fn.restype=None
            for k in range(8000):
                x=(ctypes.c_uint32*2)(k*37,k*53)
                fn(x)
                self.assertEqual(list(x),[k*53,k*37])


if __name__=='__main__': unittest.main()
