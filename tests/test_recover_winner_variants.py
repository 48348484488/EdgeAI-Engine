"""Integration and negative tests for Clang ARM32 stripped winner variants."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from recover_winner_variants import recover_variants

TRIPLETS=[[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]]
OPTS=('1','2','3','s','z')

def compile_stripped(root,optimization,text_address='0x1000'):
    source=ROOT/'examples/reverse/tictactoe.c'
    original=root/f'game_{optimization}.elf'
    stripped=root/f'stripped_{optimization}.elf'
    subprocess.run(['clang','--target=armv7-none-eabi','-marm','-O'+optimization,
                    '-fno-inline','-nostdlib','-fuse-ld=lld',
                    '-Wl,-Ttext='+text_address,'-Wl,-e,start',
                    str(source),'-o',str(original)],check=True,capture_output=True)
    subprocess.run(['llvm-objcopy','--strip-all',str(original),str(stripped)],
                   check=True,capture_output=True)
    return stripped

class WinnerVariantsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.files={x:compile_stripped(Path(cls.tmp.name),x) for x in OPTS}
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_five_optimizations_recover_same_behavior(self):
        for opt in OPTS:
            with self.subTest(opt=opt):
                result=recover_variants(self.files[opt])
                self.assertEqual(result['triplets'],TRIPLETS)
                self.assertEqual(result['loop_iterations'],8)
                self.assertEqual(result['board_cells'],9)
                self.assertEqual(result['function_address'],'0x1000')
                self.assertEqual(result['table_symbol'],None)
                if opt in ('2','3'):
                    self.assertIsNone(result['table_address'])
                    self.assertEqual(len(result['board_load_pcs']),24)
                else:
                    self.assertEqual(len(result['board_load_pcs']),3)

    def test_relocation_is_not_a_fixed_address_lookup(self):
        with tempfile.TemporaryDirectory() as temp:
            for opt in OPTS:
                with self.subTest(opt=opt):
                    file=compile_stripped(Path(temp),opt,'0x5000')
                    result=recover_variants(file)
                    self.assertEqual(result['triplets'],TRIPLETS)
                    self.assertEqual(result['function_address'],'0x5000')

    def test_unoptimized_not_falsely_claimed_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            file=compile_stripped(Path(temp),'0')
            with self.assertRaises(ValueError):
                recover_variants(file)

    def test_loop_bound_changes_reflected_in_recovered_semantics(self):
        for opt in ('1','s','z'):
            with self.subTest(opt=opt):
                data=bytearray(self.files[opt].read_bytes())
                original=bytes.fromhex('080051e3')
                self.assertEqual(data.count(original),1)
                at=data.index(original)
                data[at:at+4]=bytes.fromhex('070051e3')
                with tempfile.TemporaryDirectory() as temp:
                    file=Path(temp)/'changed.elf';file.write_bytes(data)
                    result=recover_variants(file)
                    self.assertEqual(result['loop_iterations'],7)
                    self.assertEqual(result['triplets'],TRIPLETS[:7])

    def test_unrolled_conditional_corruption_rejected(self):
        for opt in ('2','3'):
            with self.subTest(opt=opt):
                data=bytearray(self.files[opt].read_bytes())
                conditional=bytes.fromhex('03005201')
                self.assertGreaterEqual(data.count(conditional),1)
                at=data.index(conditional)
                data[at:at+4]=bytes.fromhex('030052e1')
                with tempfile.TemporaryDirectory() as temp:
                    file=Path(temp)/'changed.elf';file.write_bytes(data)
                    with self.assertRaises(ValueError):
                        recover_variants(file)

    def test_broken_oz_pc_literal_rejected(self):
        data=bytearray(self.files['z'].read_bytes())
        old=bytes.fromhex('50c09fe5')
        self.assertEqual(data.count(old),1)
        at=data.index(old)
        data[at:at+4]=bytes.fromhex('54c09fe5')
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'changed.elf';file.write_bytes(data)
            with self.assertRaises(ValueError):
                recover_variants(file)

if __name__=='__main__':
    unittest.main()
