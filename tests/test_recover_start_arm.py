"""Compiler-built ARM32 game start() recovery, adversarial negative regressions."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from recover_start_arm import recover_elf, recover_text, emit_cpp


class StartRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.elf=Path(cls.tmp.name)/'game.elf'
        subprocess.run(['clang','--target=armv7-none-eabi','-marm','-O1',
                        '-fno-inline','-nostdlib','-fuse-ld=lld',
                        '-Wl,-Ttext=0x1000','-Wl,-e=start',
                        str(ROOT/'examples/reverse/tictactoe.c'),
                        '-o',str(cls.elf)],
                       check=True,capture_output=True)
        cls.disasm=subprocess.check_output(
            ['llvm-objdump','--no-show-raw-insn','-d',str(cls.elf)],text=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_all_five_moves_come_from_compiled_game(self):
        recovered=recover_elf(self.elf)
        self.assertEqual([(r['position'],r['player']) for r in recovered['moves']],
                         [(0,1),(4,2),(1,1),(8,2),(2,1)])
        self.assertFalse(recovered['source_read'])
        self.assertTrue(recovered['moves'][-1]['tail'])
        self.assertIn('return play(2, 1)',emit_cpp(recovered))

    def test_wrong_direct_call_target_refused(self):
        corrupted=re.sub(r'(\bbl\s+)0x1074',r'\g<1>0x1000',self.disasm,count=1)
        self.assertNotEqual(corrupted,self.disasm)
        with self.assertRaisesRegex(ValueError,'target'):
            recover_text(corrupted)

    def test_unknown_arg_opcode_refused(self):
        corrupted=self.disasm.replace('mov\tr0, #4','str\tr0, #4')
        self.assertNotEqual(corrupted,self.disasm)
        with self.assertRaisesRegex(ValueError,'arguments'):
            recover_text(corrupted)

    def test_corrupt_final_tail_branch_refused(self):
        corrupted=self.disasm.replace('b\t0x1074 <play>', 'bl\t0x1074 <play>')
        self.assertNotEqual(corrupted,self.disasm)
        with self.assertRaisesRegex(ValueError,'epilogue'):
            recover_text(corrupted)

    def test_source_not_required_for_call_sequence_parser(self):
        recovered=recover_text(self.disasm)
        self.assertEqual(recovered['function'],'start')
        self.assertEqual(recovered['pattern'],'straight_line_ARM32_calls')


if __name__=='__main__':
    unittest.main()
