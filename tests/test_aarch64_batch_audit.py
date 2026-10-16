"""AArch64 batch ELF static coverage and evidence, compiler-backed and adversarial."""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from aarch64_batch_audit import run, _get_disassembly

SOURCE = """
.text
.global dispatch_test
.type dispatch_test, %function
dispatch_test:
    adrp x11, dispatch_table
    cbz x0, alternate
    nop
    b merge
alternate:
    nop
merge:
    add x11, x11, :lo12:dispatch_table
    adr x9, jump_origin
    ldrsw x10, [x11, x8, lsl #2]
    add x9, x9, x10
    br x9
jump_origin:
    ret
.size dispatch_test, . - dispatch_test
.global plain_test
.type plain_test, %function
plain_test:
    add x0, x0, #1
    cbz x1, alternate_exit
    sub x0, x0, #3
alternate_exit:
    ret
.size plain_test, . - plain_test
.section .rodata
.p2align 2
dispatch_table:
.word jump_origin - jump_origin
"""


def compile_fixture(out):
    source = out / 'fixture.S'
    obj = out / 'fixture.o'
    elf = out / 'fixture.elf'
    source.write_text(SOURCE)
    subprocess.run(['clang', '--target=aarch64-none-elf', '-c',
                    str(source), '-o', str(obj)], check=True, capture_output=True)
    subprocess.run(['clang', '--target=aarch64-none-elf', '-nostdlib',
                    '-fuse-ld=lld', '-Wl,-Ttext=0x1000', '-Wl,-e,dispatch_test',
                    str(obj), '-o', str(elf)], check=True, capture_output=True)
    return elf


@unittest.skipUnless(all(shutil.which(x) for x in ('clang', 'ld.lld', 'llvm-objdump')),
                     'requires Clang, LLD and LLVM objdump')
class CompilerBackedBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.elf = compile_fixture(self.root)

    def test_two_compiled_functions_and_metrics(self):
        result = run(self.elf, ('plain_test', 'dispatch_test'), max_functions=10)
        totals = result['summary']
        self.assertEqual(totals['functions_selected'], 2)
        self.assertEqual(totals['functions_completed'], 2)
        self.assertEqual(totals['functions_unsupported_or_skipped'], 0)
        self.assertEqual(totals['indirect_sites_in_completed_functions'], 1)
        self.assertEqual(totals['table_patterns_in_completed_functions'], 1)
        self.assertEqual(totals['common_base_candidates_in_completed_functions'], 1)
        recovered = next(f for f in result['functions'] if f['function'] == 'dispatch_test')
        text = _get_disassembly(self.elf, 0x1000, 0x2c)
        adr = re.search(r'1000:\s+adrp\s+x11,\s+(0x[0-9a-f]+)', text)
        add = re.search(r'1014:\s+add\s+x11,\s+x11,\s+#(0x[0-9a-f]+)', text)
        self.assertIsNotNone(adr)
        self.assertIsNotNone(add)
        expected_base = int(adr[1], 16) + int(add[1], 16)
        self.assertEqual(int(recovered['site_evidence'][0]['table_base_candidate'], 16),
                         expected_base)
        self.assertFalse(result['target_executed'])
        self.assertFalse(result['runtime_paths_proven'])
        self.assertEqual(len(result['file_sha256']), 64)

    def test_named_function_missing_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, 'requested function missing'):
            run(self.elf, ('not_present',))

    def test_bound_max_functions(self):
        result = run(self.elf, max_functions=1)
        self.assertEqual(result['summary']['functions_selected'], 1)
        with self.assertRaises(ValueError):
            run(self.elf, max_functions=1000)

    def test_disassembly_range_includes_internal_labels(self):
        data = _get_disassembly(self.elf, 0x1000, 0x2c)
        self.assertIn('alternate', data)
        self.assertIn('1024:', data)

    def test_one_unsupported_function_cannot_fake_a_pass(self):
        from aarch64_batch_audit import _summarize_function
        def injected(data, path, name, size):
            if name == 'plain_test':
                raise ValueError('controlled unexpected opcode')
            return _summarize_function(data, path, name, size)
        with patch('aarch64_batch_audit._summarize_function', side_effect=injected):
            result = run(self.elf, ('plain_test', 'dispatch_test'))
        self.assertEqual(result['summary']['functions_completed'], 1)
        self.assertEqual(result['summary']['functions_unsupported_or_skipped'], 1)
        self.assertTrue(any(x['status'] == 'UNSUPPORTED' for x in result['functions']))

    def test_corrupt_elf_rejected(self):
        broken = self.root / 'broken.elf'
        broken.write_bytes(b'x' * 128)
        with self.assertRaisesRegex(ValueError, 'expected little endian'):
            run(broken)

    def test_empty_selection_rejected_on_exact_name(self):
        with self.assertRaisesRegex(ValueError, 'requested function missing'):
            run(self.elf, ('ret',))


if __name__ == '__main__':
    unittest.main()
