import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recover_winner', ROOT/'tools/recover_winner.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class WinnerRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.elf = Path(cls.directory.name) / 'test.elf'
        subprocess.run(['clang', '--target=armv7-none-eabi', '-marm', '-O1',
                        '-fno-inline', '-nostdlib', '-fuse-ld=lld',
                        '-Wl,-Ttext=0x1000', '-Wl,-e=start',
                        str(ROOT/'examples/reverse/tictactoe.c'), '-o', str(cls.elf)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_recovers_eight_triplets_from_elf(self):
        result = mod.recover(self.elf)
        self.assertEqual(result['triplets'], [
            [0,1,2],[3,4,5],[6,7,8],[0,3,6],
            [1,4,7],[2,5,8],[0,4,8],[2,4,6]
        ])
        self.assertEqual(result['loop_iterations'], 8)
        self.assertEqual(len(result['board_load_pcs']), 3)
        cpp = mod.emit_cpp(result)
        self.assertIn('{2, 4, 6}', cpp)
        self.assertIn('if (a != 0 && a == b && b == c)', cpp)

    def test_out_of_range_triplet_rejected(self):
        source = self.elf.read_bytes()
        pattern = bytes(i for row in mod.recover(self.elf)['triplets'] for i in row)
        where = source.find(pattern)
        self.assertGreater(where, 0)
        corrupted = bytearray(source)
        corrupted[where] = 99
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / 'bad.elf'
            file.write_bytes(corrupted)
            with self.assertRaisesRegex(ValueError, 'outside board'):
                mod.recover(file)

    def test_missing_elf_symbols_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / 'stripped.elf'
            subprocess.run(['llvm-objcopy', '--strip-all', str(self.elf), str(file)],
                           check=True, capture_output=True)
            with self.assertRaisesRegex(ValueError, 'symbol'):
                mod.recover(file)

    def test_changed_compiler_loop_bound_rejected(self):
        source = self.elf.read_bytes()
        original = bytes.fromhex('080051e3')  # cmp r1, #8 in little-endian ARM32
        self.assertEqual(source.count(original), 1)
        mutated = source.replace(original, bytes.fromhex('070051e3'))
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / 'changed.elf'
            file.write_bytes(mutated)
            with self.assertRaisesRegex(ValueError, 'loop bound'):
                mod.recover(file)


if __name__ == '__main__':
    unittest.main()
