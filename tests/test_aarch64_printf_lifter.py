"""Fail-closed tests of source-blind ARM64 printf/libc literal reconstruction.

Optional integration tests use a pinned external stripped 2048 ELF obtained
separately from the public GitHub Actions artifact; no source is an input.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from aarch64_printf_lifter import (format_arg_count,get_cstring,load_rodata,
                                  plt_symbols,run)

PINNED='a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b'
ENV=os.environ.get('EDGEAI_BLIND_2048_ELF','')
ELF=Path(ENV) if ENV else Path(__file__).resolve().parents[1]/'bin/2048-arm64-stripped.elf'
INTEGRATION=ELF.is_file() and shutil.which('llvm-objdump') is not None
OUTPUTS={
    'win':bytes.fromhex('1b5b313b3138481b5b313b33366d596f752077696e20211b5b306d'),
    'over':bytes.fromhex('1b5b313b3138481b5b313b33316d47414d45204f5645521b5b306d'),
}


class FormatGuardTests(unittest.TestCase):
    def test_only_small_d_formats(self):
        self.assertEqual(format_arg_count(b'\x1b[%d;%dH'),2)
        self.assertEqual(format_arg_count(b'%%100 %+04d'),1)

    def test_rejects_unsafe_or_unmodeled_formats(self):
        for data in (b'%n',b'%s',b'%p',b'%f',b'%lld',b'%9999d',b'%d'*5):
            with self.subTest(data=data),self.assertRaises(ValueError):
                format_arg_count(data)

    def test_elf_rodata_bounds(self):
        with self.assertRaisesRegex(ValueError,'outside ELF'):
            get_cstring(0x99999,(0x1000,b'HELLO\x00'))

    def test_rejects_nul_missing(self):
        with self.assertRaisesRegex(ValueError,'not NUL terminated'):
            get_cstring(0x1000,(0x1000,b'NO TERMINATOR'))

    def test_rejects_blank_format(self):
        with self.assertRaisesRegex(ValueError,'empty printf format'):
            get_cstring(0x1000,(0x1000,b'\x00abc'))

    def test_rejects_non_elf(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.elf';p.write_bytes(b'X'*256)
            with self.assertRaisesRegex(ValueError,'ELF64'):
                load_rodata(p)


@unittest.skipUnless(INTEGRATION,'set EDGEAI_BLIND_2048_ELF to pinned stripped ELF')
class BinaryOnlyIntegrationTests(unittest.TestCase):
    def test_verified_elf_and_dynamic_printf_import(self):
        self.assertEqual(hashlib.sha256(ELF.read_bytes()).hexdigest(),PINNED)
        self.assertEqual(plt_symbols(ELF)[0x400830],'__printf_chk')

    def test_extracted_formats_match_binary_not_templates(self):
        rodata=load_rodata(ELF)
        self.assertEqual(get_cstring(0x401ab8,rodata),b'You win !')
        self.assertEqual(get_cstring(0x401ac8,rodata),b'GAME OVER')

    def test_recovery_emits_two_exact_23_instruction_wrappers(self):
        for address in (0x4015f4,0x401650):
            cpp,evidence=run(ELF,address)
            self.assertIn(f'recovered_{address:x}',cpp)
            self.assertFalse(evidence['source_read'])
            self.assertFalse(evidence['symbols_used'])
            self.assertEqual(evidence['instructions_translated'],23)
            self.assertEqual(len(evidence['calls']),4)

    def test_change_rodata_changes_generated_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'altered.elf'
            data=ELF.read_bytes();self.assertEqual(data.count(b'You win !\x00'),1)
            p.write_bytes(data.replace(b'You win !\x00',b'Hello AI!\x00'))
            old,_=run(ELF,0x4015f4)
            new,_=run(p,0x4015f4)
            self.assertNotEqual(old,new)

    @unittest.skipUnless(shutil.which('g++'),'native C++ compiler required')
    def test_native_binary_output_against_independent_oracle_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for addr in (0x4015f4,0x401650):
                code,_=run(ELF,addr)
                (p/f'candidate_{addr:x}.cpp').write_text(code)
            driver=p/'driver.cpp'
            driver.write_text('#include <cstring>\n'
                'extern "C" void recovered_4015f4();\n'
                'extern "C" void recovered_401650();\n'
                'int main(int n,char**a){if(n!=2)return 2;'
                'if(!std::strcmp(a[1],"win")) recovered_4015f4();'
                'else if(!std::strcmp(a[1],"over")) recovered_401650();'
                'else return 2;return 0;}\n')
            out=p/'generated'
            subprocess.run(['g++','-O2','-std=c++17',
                            str(driver),str(p/'candidate_4015f4.cpp'),
                            str(p/'candidate_401650.cpp'),'-o',str(out)],
                           capture_output=True,check=True)
            for action,reference in OUTPUTS.items():
                result=subprocess.check_output([str(out),action])
                self.assertEqual(result,reference)
                self.assertEqual(len(result),27)


if __name__=='__main__':
    unittest.main()
