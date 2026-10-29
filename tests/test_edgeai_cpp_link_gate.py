import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from edgeai_cpp_link_gate import probe


@unittest.skipUnless(shutil.which('g++') and shutil.which('nm'), 'host C++ toolchain required')
class NativeGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def write(self, name, source):
        (self.path / name).write_text(source)

    def test_valid_export(self):
        self.write('candidate_2000.cpp', 'extern "C" int recovered_2000(){return 42;}')
        r = probe(self.path, strict_link=True)
        self.assertTrue(r['passed'])
        self.assertTrue(r['strict_link']['passed'])
        self.assertFalse(r['arm64_qemu_parity_tested'])

    def test_prototype_only_rejected(self):
        self.write('candidate_2000.cpp', 'extern "C" int recovered_2000();')
        self.assertFalse(probe(self.path)['passed'])

    def test_comment_forgery_rejected(self):
        self.write('candidate_2000.cpp', '// extern "C" int recovered_2000(){return 1;}\nint x=2;')
        self.assertFalse(probe(self.path)['passed'])

    def test_string_forgery_rejected(self):
        self.write('candidate_2000.cpp', 'const char* x="extern \\"C\\" int recovered_2000(){return 1;}";')
        self.assertFalse(probe(self.path)['passed'])

    def test_mangled_cpp_symbol_rejected(self):
        self.write('candidate_2000.cpp', 'int recovered_2000(){return 1;}')
        self.assertFalse(probe(self.path)['passed'])

    def test_variable_symbol_rejected(self):
        self.write('candidate_2000.cpp', 'extern "C" int recovered_2000=1;')
        self.assertFalse(probe(self.path)['passed'])

    def test_invalid_syntax_rejected(self):
        self.write('candidate_2000.cpp', 'extern "C" int recovered_2000(){ broken; }')
        self.assertFalse(probe(self.path)['passed'])

    def test_unresolved_external_rejected_by_strict_link(self):
        self.write('candidate_2000.cpp', 'extern "C" int absent(); extern "C" int recovered_2000(){return absent();}')
        self.assertTrue(probe(self.path)['passed'])
        r = probe(self.path, strict_link=True)
        self.assertTrue(r['all_exports_verified'])
        self.assertFalse(r['strict_link']['passed'])
        self.assertFalse(r['passed'])

    def test_multi_file_link_succeeds(self):
        self.write('candidate_2000.cpp', 'extern "C" int recovered_3000(); extern "C" int recovered_2000(){return recovered_3000();}')
        self.write('candidate_3000.cpp', 'extern "C" int recovered_3000(){return 7;}')
        self.assertTrue(probe(self.path, strict_link=True)['passed'])

    def test_duplicate_address_case_rejected(self):
        self.write('candidate_2000.cpp', 'extern "C" int recovered_2000(){return 1;}')
        self.write('candidate_02000.cpp', 'extern "C" int recovered_2000(){return 1;}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            probe(self.path)

    def test_empty_directory_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no candidate'):
            probe(self.path)

    def test_native_cli_exit_code(self):
        self.write('candidate_2000.cpp', 'extern "C" int recovered_2000(){return 1;}')
        out = self.path / 'report.json'
        script = Path(__file__).resolve().parents[1] / 'tools' / 'edgeai_cpp_link_gate.py'
        p = subprocess.run([sys.executable, str(script), '--generated-dir', str(self.path),
                            '--strict-link', '--output', str(out)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(json.loads(out.read_text())['passed'])


if __name__ == '__main__':
    unittest.main()
