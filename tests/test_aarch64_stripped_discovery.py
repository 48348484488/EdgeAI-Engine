"""Fail-closed and compiler-backed tests of stripped ELF entry discovery."""
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
from aarch64_stripped_discovery import analyze, branch_imm26, load_text, _start_main_pointer_candidate


class DecoderTests(unittest.TestCase):
    def test_forward_and_backward_bl_offsets(self):
        self.assertEqual(branch_imm26(0x1000, 0x94000001), 0x1004)
        self.assertEqual(branch_imm26(0x1000, 0x97FFFFFF), 0x0FFC)

    def test_reject_non_elf(self):
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp) / 'bad.elf'
            bad.write_bytes(b'X' * 128)
            with self.assertRaisesRegex(ValueError, 'expected little-endian ELF64'):
                load_text(bad)

    def test_entry_function_pointer_to_trampoline(self):
        code = bytearray(64)
        # ADRP x0,page; ADD x0,x0,#0x20; BL distant PLT; x0 -> NOP/B thunk.
        struct.pack_into('<III', code, 0, 0x90000000, 0x91008000, 0x9403FFFE)
        struct.pack_into('<II', code, 32, 0xd503201f, 0x14000003)
        result = _start_main_pointer_candidate(0x400000, code, 0x400000)
        self.assertEqual(result, 0x400020)
        with patch('aarch64_stripped_discovery.load_text', return_value={
            'text_address': 0x400000, 'text': code, 'elf_entry': 0x400000,
            'sha256': 'e' * 64, 'elf_type': 2,
        }):
            scan = analyze('ignored-unopened.elf')
        matched = next(x for x in scan['candidate_entries'] if x['address'] == '0x400030')
        self.assertIn('crt_main_pointer_thunk_target', matched['evidence'])
        self.assertFalse(scan['source_read'])
        self.assertFalse(scan['symbols_used'])

    def test_no_unsupported_adrp_guesses(self):
        data = bytearray(64)
        struct.pack_into('<III', data, 0, 0x90000000, 0x91008000, 0xd503201f)
        self.assertIsNone(_start_main_pointer_candidate(0x400000, data, 0x400000))


@unittest.skipUnless(shutil.which('clang') and shutil.which('ld.lld'),
                     'requires Clang/LLD AArch64 ELF linker')
class CompilerBackedTests(unittest.TestCase):
    def test_real_bare_metal_stripped_elf_calls_and_prologue(self):
        source = '''.text
.global _start
_start:
    bl entry_one
    b end
entry_one:
    stp x29, x30, [sp, #-16]!
    mov x29, sp
    bl entry_two
    ldp x29, x30, [sp], #16
    ret
entry_two:
    add w0, w0, #1
    ret
end:
    mov w0, #0
    ret
'''
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out/'fixture.S').write_text(source)
            subprocess.run(['clang', '--target=aarch64-none-elf', '-nostdlib',
                            '-fuse-ld=lld', '-Wl,-Ttext=0x1000', '-Wl,-e,_start',
                            '-Wl,--strip-all', str(out/'fixture.S'), '-o', str(out/'fixture.elf')],
                           capture_output=True, text=True, check=True)
            scan = analyze(out/'fixture.elf')
            addrs = [int(x['address'], 16) for x in scan['candidate_entries']]
            entry = load_text(out/'fixture.elf')['elf_entry']
            self.assertIn(entry, addrs)
            self.assertIn(entry + 8, addrs)
            self.assertIn(entry + 28, addrs)
            self.assertEqual(scan['direct_bl_targets_within_text'], 2)
            self.assertFalse(scan['original_source_decompiled'])


if __name__ == '__main__':
    unittest.main()
