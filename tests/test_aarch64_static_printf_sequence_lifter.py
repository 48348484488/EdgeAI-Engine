"""Source-blind AArch64 static printer regression and independent C oracle tests.

Set EDGEAI_BLIND_2048_ELF to the extracted stripped ELF to enable integration.
The oracle is used only AFTER the emitted C++ is available.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from aarch64_static_printf_sequence_lifter import run,printf_items,_frame_evidence

ELF=Path(os.environ.get('EDGEAI_BLIND_2048_ELF',str(ROOT/'bin/2048-arm64-stripped.elf')))
ORACLE=ROOT/'tests/oracles/2048_indicators_oracle.c'
EXPECTED_SHA='a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b'
OUTPUT_SHA='efe0f74688616d2beff9ec51022e0a68bb849c6c5269bdf4f9388f04a31be559'
CAN_RUN=ELF.is_file() and shutil.which('llvm-objdump') is not None


class FormatAndFrameTests(unittest.TestCase):
    def test_supported_roles(self):
        self.assertEqual(printf_items(b'%*s'),['int','cstring'])
        self.assertEqual(printf_items(b'%d / %s %%'),['int','cstring'])
        self.assertEqual(printf_items(b'no specifier'),[])

    def test_reject_unmodeled_printf_formats(self):
        for fmt in (b'%n',b'%x',b'%p',b'%f',b'%lld',b'%9999d',b'%*s%*s%d'):
            with self.subTest(fmt=fmt),self.assertRaises(ValueError):
                printf_items(fmt)

    def test_reject_more_than_four_args(self):
        with self.assertRaisesRegex(ValueError,'too many'):
            printf_items(b'%d%d%d%d%d')

    def test_reject_utf8_error(self):
        with self.assertRaisesRegex(ValueError,'UTF-8'):
            printf_items(b'\xff%d')

    def test_reject_unbalanced_frame(self):
        with self.assertRaises(ValueError):
            _frame_evidence([(0x1000,'stp','x29, x30, [sp, #-0x30]!'),
                             (0x1004,'mov','x29, sp'),
                             (0x1008,'stp','x19, x20, [sp, #0x10]'),
                             (0x100c,'mov','w0, #1'),
                             (0x1010,'ldp','x29, x30, [sp], #0x30'),
                             (0x1014,'ret','')])

    def test_generator_has_no_original_source_or_known_game_addresses(self):
        text=(ROOT/'tools/aarch64_static_printf_sequence_lifter.py').read_text()
        self.assertNotIn('oracle_POST_GENERATION_ONLY',text)
        self.assertNotIn('2048_indicators_oracle',text)
        self.assertNotIn('401484',text)
        self.assertNotIn('print_indicators',text)


@unittest.skipUnless(CAN_RUN,'extract pinned stripped ELF and set EDGEAI_BLIND_2048_ELF')
class ActualELFTests(unittest.TestCase):
    def test_real_92_instruction_function_from_stripped_elf(self):
        self.assertEqual(hashlib.sha256(ELF.read_bytes()).hexdigest(),EXPECTED_SHA)
        cpp,data=run(ELF,0x401484)
        self.assertEqual(data['input_sha256'],EXPECTED_SHA)
        self.assertEqual(data['instructions_translated'],92)
        self.assertEqual(data['printf_calls'],18)
        self.assertFalse(data['symbols_used'])
        self.assertFalse(data['source_read'])
        self.assertNotIn('print_indicators',cpp)

    def test_reject_different_function_with_unknown_memory_effects(self):
        with self.assertRaises(ValueError):
            run(ELF,0x400bfc)

    def test_change_elf_rodata_changes_cpp(self):
        data=ELF.read_bytes()
        self.assertEqual(data.count(b'ack\x00'),1)
        with tempfile.TemporaryDirectory() as temp:
            modified=Path(temp)/'modified.elf'
            modified.write_bytes(data.replace(b'ack\x00',b'AI!\x00'))
            original,_=run(ELF,0x401484)
            updated,meta=run(modified,0x401484)
            self.assertNotEqual(original,updated)
            self.assertEqual(meta['printf_calls'],18)

    @unittest.skipUnless(shutil.which('gcc') and shutil.which('g++'),
                         'requires native gcc and g++')
    def test_byte_for_byte_independent_original_c_stdout(self):
        self.assertTrue(ORACLE.is_file())
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            cpp,_=run(ELF,0x401484)
            (root/'generated.cpp').write_text(cpp)
            (root/'driver.cpp').write_text(
                'extern "C" void recovered_401484();\n'
                'int main() { recovered_401484(); return 0; }\n')
            subprocess.run(['g++','-O2','-std=c++17',str(root/'driver.cpp'),
                            str(root/'generated.cpp'),'-o',str(root/'generated')],
                           check=True,capture_output=True)
            subprocess.run(['gcc','-O2','-std=c11',str(ORACLE),'-o',str(root/'reference')],
                           check=True,capture_output=True)
            actual=subprocess.check_output([str(root/'generated')])
            reference=subprocess.check_output([str(root/'reference')])
            self.assertEqual(actual,reference)
            self.assertEqual(len(actual),126)
            self.assertEqual(hashlib.sha256(actual).hexdigest(),OUTPUT_SHA)


if __name__=='__main__': unittest.main()
