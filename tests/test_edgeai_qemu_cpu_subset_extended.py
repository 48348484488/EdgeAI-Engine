"""Fail-closed regressions for decoded ARM64 immediate memory loads and CBZ/CBNZ.

These tests use original AArch64 instruction semantics and synthetic
instruction streams to verify the extended QEMU CPU-state differential
interpreter without consulting original game source.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from edgeai_qemu_cpu_state_differential import run_interpreter


class CpuExtendedSubset(unittest.TestCase):
    def test_immediate_load_last_board_word_and_cbz(self):
        code={
            0x1000:('mov','x2, x0'),
            0x1004:('ldr','w1, [x2, #0x3c]'),
            0x1008:('cbz','w1, 0x1014'),
            0x100c:('mov','w0, #1'),
            0x1010:('ret',''),
            0x1014:('mov','w0, #0'),
            0x1018:('ret','')}
        for tail,expected in [(0,0),(1,1),(2048,1)]:
            with self.subTest(tail=tail):
                board=[2]*15+[tail]
                states,ret=run_interpreter(code,0x1000,board)
                self.assertEqual(ret,expected)
                self.assertEqual(states[1]['pc'],'0x1004')

    def test_cbnz_branches_when_last_word_is_nonzero(self):
        code={
            0x2000:('ldr','w1, [x0, #0x3c]'),
            0x2004:('cbnz','w1, 0x2010'),
            0x2008:('mov','w0, #0'),
            0x200c:('ret',''),
            0x2010:('mov','w0, #1'),
            0x2014:('ret','')}
        self.assertEqual(run_interpreter(code,0x2000,[0]*16)[1],0)
        self.assertEqual(run_interpreter(code,0x2000,[0]*15+[2])[1],1)

    def test_inverted_cbz_detected_as_first_pc_error(self):
        code={
            0x3000:('ldr','w1, [x0]'),
            0x3004:('cbz','w1, 0x3010'),
            0x3008:('mov','w0, #0'),
            0x300c:('ret',''),
            0x3010:('mov','w0, #1'),
            0x3014:('ret','')}
        correct,_=run_interpreter(code,0x3000,[0]*16)
        broken,_=run_interpreter(code,0x3000,[0]*16,invert_equal=True)
        self.assertNotEqual(correct[2]['pc'],broken[2]['pc'])
        self.assertEqual(correct[2]['pc'],'0x3010')
        self.assertEqual(broken[2]['pc'],'0x3008')

    def test_out_of_bounds_word_load_is_rejected(self):
        code={0x4000:('ldr','w1, [x0, #0x40]'),
              0x4004:('ret','')}
        with self.assertRaisesRegex(ValueError,'memory outside'):
            run_interpreter(code,0x4000,[0]*16)

    def test_unknown_instruction_rejected(self):
        code={0x5000:('str','w0, [x1]'),0x5004:('ret','')}
        with self.assertRaisesRegex(ValueError,'unknown ARM64'):
            run_interpreter(code,0x5000,[0]*16)


if __name__=='__main__':unittest.main()
