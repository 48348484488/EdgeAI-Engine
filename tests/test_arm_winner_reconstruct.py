import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('winner_recon',ROOT/'tools'/'arm_winner_reconstruct.py')
reconstruct=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconstruct)

class TestWinnerReconstruction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.elf=Path(cls.tmp.name)/'game.elf'
        subprocess.run(['clang','--target=armv7-none-eabi','-marm','-O1','-fno-inline',
            '-nostdlib','-fuse-ld=lld','-Wl,-Ttext=0x1000','-Wl,-e,start',
            str(ROOT/'examples/reverse/tictactoe.c'),'-o',str(cls.elf)],
            check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_extract_from_real_arm_elf(self):
        try:
            result=reconstruct.reconstruct(self.elf)
        except ValueError:
            # A different LLVM version may emit a different instruction
            # sequence. Preserve the exact disassembly in CI diagnostics.
            entry, instructions=reconstruct._disassembly(self.elf)
            print('WINNER_ARM_DIAGNOSTIC_ENTRY',hex(entry),flush=True)
            for pc, mnemonic, operands in instructions:
                print('WINNER_ARM_DIAGNOSTIC',hex(pc),mnemonic,operands,flush=True)
            raise
        self.assertEqual(result['evidence']['instruction_count'],29)
        self.assertEqual(len(result['evidence']['winning_triplets']),8)
        self.assertEqual(result['evidence']['winning_triplets'][0],[0,1,2])
        self.assertIn('if (a != 0 && a == b && b == c)',result['cpp'])

    def test_corrupt_table_rejected(self):
        blob=bytearray(self.elf.read_bytes())
        syms,sections=reconstruct._symbols_and_sections(blob)
        info=syms['winner.lines'];sh=sections[info['section']]
        off=sh[4]+info['address']-sh[3]
        blob[off]=9
        damaged=Path(self.tmp.name)/'corrupt_table.elf'
        damaged.write_bytes(blob)
        with self.assertRaisesRegex(ValueError,'invalid winner lookup table'):
            reconstruct.reconstruct(damaged)

    def test_changed_loop_bound_rejected(self):
        blob=bytearray(self.elf.read_bytes())
        syms,sections=reconstruct._symbols_and_sections(blob)
        info=syms['winner'];sh=sections[info['section']]
        code_off=sh[4]+info['address']-sh[3]
        needle=bytes.fromhex('080051e3')
        off=blob.find(needle,code_off,code_off+info['size'])
        self.assertNotEqual(off,-1)
        blob[off]=9
        modified=Path(self.tmp.name)/'changed_bound.elf'
        modified.write_bytes(blob)
        with self.assertRaisesRegex(ValueError,'unverified winner ARM opcode'):
            reconstruct.reconstruct(modified)

if __name__=='__main__':unittest.main()
