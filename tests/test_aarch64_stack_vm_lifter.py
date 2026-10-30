"""Tests for source-blind ARM64 stack, rand, callgraph, and emitted native C++.

Original C oracle is loaded ONLY after the C++ files have been produced.
"""
import ctypes as c
import hashlib
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from aarch64_stack_vm_lifter import (generate, select_pair, locate_guard_got, address, lower)

ROOT=Path(__file__).resolve().parent.parent
STRIPPED=Path(os.environ.get('EDGEAI_BLIND_2048_ELF',str(ROOT/'bin/2048-arm64-stripped.elf')))
ORACLE=ROOT/'tests/oracles/2048_board_rand_subset.c'
EXPECTED='a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b'

class StrictSubsetTests(unittest.TestCase):
    def test_reject_unknown_memory_mode(self):
        with self.assertRaisesRegex(ValueError, 'bad index modifier'):
            address('[x0, x1, lsl #7]')

    def test_reject_unknown_opcode(self):
        with self.assertRaisesRegex(ValueError, 'unsupported opcode'):
            lower(0x1000,'svc','#0',set(),{},0)

    def test_unsupported_external_call_is_not_stubbed(self):
        with self.assertRaisesRegex(ValueError,'unknown external'):
            lower(0x1000,'bl','0x8000',set(),{},0)

    def test_signed_shift_uses_signed_cast_before_shifting(self):
        line=lower(0x1000,'asr','x1, x1, #34',{0x1000},{},0)
        self.assertIn('static_cast<int64_t>',line)
        self.assertIn(' >> 34',line)

    def test_no_original_game_name_templates(self):
        source=(ROOT/'tests/aarch64_stack_vm_lifter.py').read_text()
        for name in ('board_add_piece','board_init','src/board.c','0x400bfc','0x400d08','0x41ffd8'):
            self.assertNotIn(name,source)

@unittest.skipUnless(STRIPPED.is_file(),'requires pinned stripped ELF')
class ActualELFTests(unittest.TestCase):
    def test_binary_hash_and_located_callgraph(self):
        self.assertEqual(hashlib.sha256(STRIPPED.read_bytes()).hexdigest(),EXPECTED)
        report,plt,functions,leaf,caller=select_pair(STRIPPED)
        self.assertEqual((leaf,caller),(0x400bfc,0x400d08))
        self.assertEqual((len(functions[leaf]),len(functions[caller])),(67,20))
        self.assertEqual(locate_guard_got(STRIPPED),0x41ffd8)

    def test_discovered_codegen_and_reproducibility(self):
        leaf,caller,cpp1,cpp2,report=generate(STRIPPED)
        self.assertFalse(report['source_read'])
        self.assertFalse(report['symbols_used'])
        self.assertEqual(report['callee_instructions']+report['caller_instructions'],87)
        self.assertIn('r[30]',cpp1)
        self.assertIn('case 0x400c84ULL:',cpp1)
        self.assertIn('std::rand()',cpp1)
        self.assertNotIn('board_add_piece',cpp1)
        self.assertIn('recovered_400d08',cpp2)
        self.assertEqual(cpp1,generate(STRIPPED)[2])

    def test_mutating_machine_code_changes_emitted_cpp(self):
        raw=bytearray(STRIPPED.read_bytes())
        # The ELF .text section's virtual address and file offset are from
        # section metadata; here inspect the instruction at the chosen PC.
        machine_addr=0x400cc4
        file_off=machine_addr-0x400000
        opcode=struct.unpack_from('<I',raw,file_off)[0]
        self.assertEqual(opcode,0x52800040) # mov w0, #2
        struct.pack_into('<I',raw,file_off,0x52800080) # mov w0, #4
        with tempfile.TemporaryDirectory() as tmp:
            altered=Path(tmp)/'modified.elf';altered.write_bytes(raw)
            original=generate(STRIPPED)[2]
            new=generate(altered)[2]
            self.assertNotEqual(original,new)
            self.assertIn('4ULL',new)

    def test_dynamic_guard_missing_fails_closed(self):
        raw=STRIPPED.read_bytes()
        self.assertEqual(raw.count(b'__stack_chk_guard\x00'),1)
        with tempfile.TemporaryDirectory() as tmp:
            altered=Path(tmp)/'modified.elf'
            altered.write_bytes(raw.replace(b'__stack_chk_guard\x00',b'__stack_chk_gourd\x00'))
            with self.assertRaisesRegex(ValueError,'__stack_chk_guard'):
                generate(altered)

    @unittest.skipUnless(shutil.which('g++') and shutil.which('gcc'),'native compilers required')
    def test_100000_differential_seeded_games_and_rand_state(self):
        self.assertTrue(ORACLE.is_file())
        leaf,caller,cpp1,cpp2,report=generate(STRIPPED)
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            (work/'leaf.cpp').write_text(cpp1)
            (work/'caller.cpp').write_text(cpp2)
            subprocess.run(['g++','-std=c++17','-O2','-fPIC','-shared',
                            str(work/'leaf.cpp'),str(work/'caller.cpp'),'-o',str(work/'candidate.so')],
                           check=True,capture_output=True,text=True)
            subprocess.run(['gcc','-std=c11','-O2','-fPIC','-shared',str(ORACLE),'-o',str(work/'oracle.so')],
                           check=True,capture_output=True,text=True)
            generated=c.CDLL(str(work/'candidate.so'))
            reference=c.CDLL(str(work/'oracle.so'))
            libc=c.CDLL(None)
            functions=[(generated.recovered_400bfc,reference.board_add_piece),
                       (generated.recovered_400d08,reference.board_init)]
            for native,oracle in functions:
                native.argtypes=[c.POINTER(c.c_uint32)]
                oracle.argtypes=[c.POINTER(c.c_uint32)]
                native.restype=oracle.restype=None
            rng=random.Random(13004433)
            checks=0
            for fun_index,(native,oracle) in enumerate(functions):
                for seed in range(50000):
                    # 1..16 empty cells, seeded and shuffled independently
                    empties=1+(seed%16)
                    cells=[0]*empties+[rng.choice([2,4,8,16,32,64,128,256,512,1024,2048]) for _ in range(16-empties)]
                    rng.shuffle(cells)
                    # init must erase whatever board existed
                    if fun_index==1 and seed%4==0:
                        cells=[rng.randrange(1,2**32) for _ in range(16)]
                    sentinel_a=0xA5A5A5A5; sentinel_b=0x5A5A5A5A
                    oracle_mem=(c.c_uint32*20)(sentinel_a,sentinel_b,*cells,sentinel_b,sentinel_a)
                    gen_mem=(c.c_uint32*20)(sentinel_a,sentinel_b,*cells,sentinel_b,sentinel_a)
                    o_board=c.cast(c.byref(oracle_mem,8),c.POINTER(c.c_uint32))
                    g_board=c.cast(c.byref(gen_mem,8),c.POINTER(c.c_uint32))
                    libc.srand(seed*13+fun_index)
                    oracle(o_board)
                    oracle_next=libc.rand()
                    libc.srand(seed*13+fun_index)
                    native(g_board)
                    generated_next=libc.rand()
                    self.assertEqual(list(gen_mem),list(oracle_mem),f'mismatch function {fun_index}, seed {seed}')
                    self.assertEqual(generated_next,oracle_next,f'rand state mismatch seed {seed}')
                    checks+=1
            self.assertEqual(checks,100000)

if __name__=='__main__':unittest.main()
