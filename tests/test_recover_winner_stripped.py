import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from recover_winner import elf_symbols
from recover_winner_stripped import recover_stripped


class StrippedWinnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.orig = Path(cls.directory.name)/'original.elf'
        cls.stripped = Path(cls.directory.name)/'stripped.elf'
        subprocess.run(['clang','--target=armv7-none-eabi','-marm','-O1',
                        '-fno-inline','-nostdlib','-fuse-ld=lld',
                        '-Wl,-Ttext=0x1000','-Wl,-e,start',
                        str(ROOT/'examples/reverse/tictactoe.c'),'-o',str(cls.orig)],
                       capture_output=True, check=True)
        subprocess.run(['llvm-objcopy','--strip-all',str(cls.orig),str(cls.stripped)],
                       capture_output=True, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_recovers_without_symtab(self):
        self.assertEqual(elf_symbols(self.stripped.read_bytes()), {})
        result = recover_stripped(self.stripped)
        self.assertEqual(result['triplets'], [[0,1,2],[3,4,5],[6,7,8],[0,3,6],
                                              [1,4,7],[2,5,8],[0,4,8],[2,4,6]])
        self.assertEqual(result['loop_iterations'], 8)
        self.assertEqual(len(result['board_load_pcs']), 3)
        self.assertEqual(result['table_symbol'], None)

    def corrupt_and_check(self, expected):
        buf = bytearray(self.stripped.read_bytes())
        self.assertGreater(buf.count(expected), 0)
        replacement = expected[:-1] + bytes([(expected[-1]+1)&255])
        where = buf.index(expected)
        buf[where:where+len(expected)] = replacement
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'mutated.elf'
            path.write_bytes(buf)
            with self.assertRaises(ValueError):
                recover_stripped(path)

    def test_bad_index_rejected(self):
        buf = bytearray(self.stripped.read_bytes())
        pattern=bytes([0,1,2,3,4,5,6,7,8,0,3,6,1,4,7,2,5,8,0,4,8,2,4,6])
        self.assertEqual(buf.count(pattern),1)
        buf[buf.index(pattern)]=99
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'bad.elf';file.write_bytes(buf)
            with self.assertRaises(ValueError):
                recover_stripped(file)

    def test_corrupt_loop_bound_rejected(self):
        self.corrupt_and_check(bytes.fromhex('080051e3'))

    def test_corrupt_table_base_rejected(self):
        buf=bytearray(self.stripped.read_bytes())
        # Find the real MOVW r12 encoding in this compiler's disassembly;
        # LLVM17/LLVM18 place the table at different addresses.
        dump=subprocess.run(['llvm-objdump','-d',str(self.orig)],
                            capture_output=True,text=True,check=True).stdout
        import re
        match=re.search(r'^\s*[0-9a-fA-F]+:\s+([0-9a-fA-F]{8})\s+movw\s+r12,',dump,re.M)
        self.assertIsNotNone(match)
        word=int(match[1],16)
        ins=word.to_bytes(4,'little')
        self.assertEqual(buf.count(ins),1)
        off=buf.index(ins)
        # Change high MOVW immediate nibble; pointer no longer maps to table.
        buf[off:off+4]=(word ^ 0x00010000).to_bytes(4,'little')
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'bad.elf';file.write_bytes(buf)
            with self.assertRaises(ValueError):
                recover_stripped(file)

    def test_relinked_executable_without_fixed_addresses(self):
        with tempfile.TemporaryDirectory() as td:
            original=Path(td)/'relocated.elf'
            stripped=Path(td)/'relocated_stripped.elf'
            subprocess.run(['clang','--target=armv7-none-eabi','-marm','-O1',
                            '-fno-inline','-nostdlib','-fuse-ld=lld',
                            '-Wl,-Ttext=0x5000','-Wl,-e,start',
                            str(ROOT/'examples/reverse/tictactoe.c'),'-o',str(original)],
                           capture_output=True,check=True)
            subprocess.run(['llvm-objcopy','--strip-all',str(original),str(stripped)],
                           capture_output=True,check=True)
            result=recover_stripped(stripped)
            self.assertEqual(result['function_address'],'0x5000')
            self.assertEqual(result['table_address'],'0x15108')
            self.assertEqual(result['board_address'],'0x25120')
            self.assertEqual(result['triplets'],recover_stripped(self.stripped)['triplets'])

    def test_invalid_elf_header_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'bad.elf';file.write_bytes(b'bad')
            with self.assertRaises(ValueError):recover_stripped(file)


if __name__=='__main__':unittest.main()
