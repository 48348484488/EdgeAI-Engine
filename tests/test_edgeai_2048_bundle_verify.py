"""V28 regression suite: published bytes must match independent evidence."""
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from edgeai_2048_bundle_verify import verify
from edgeai_2048_v15_recovery import rebuild
from test_edgeai_2048_v15_recovery import GENERATOR


class BundleIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.elf = self.root / 'original.elf'
        self.elf.write_bytes(b'fixture ELF')
        self.tool = self.root / 'tools'
        self.tool.mkdir()
        (self.tool / 'aarch64_multistage_batch.py').write_text(GENERATOR)
        gate = Path(__file__).resolve().parents[1] / 'tools' / 'edgeai_cpp_link_gate.py'
        (self.tool / gate.name).write_bytes(gate.read_bytes())
        self.bundle = self.root / 'bundle'
        rebuild(self.elf, self.bundle, self.tool, expected_count=2,
                expected_elf_sha256=hashlib.sha256(self.elf.read_bytes()).hexdigest())

    def test_valid_bundle_verified_against_elf(self):
        report = verify(self.bundle, self.elf)
        self.assertTrue(report['passed'])
        self.assertEqual(report['files_verified'], 5)
        self.assertFalse(report['whole_game_recovered'])

    def _rehash_library(self):
        manifest_path = self.bundle / 'bundle_manifest.json'
        manifest = json.loads(manifest_path.read_text())
        p = self.bundle / 'recovered_candidates.so'
        manifest['files'][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))

    def test_valid_bundle_has_real_native_exports(self):
        self.assertEqual(verify(self.bundle)['native_exports_verified_from_elf'], 2)

    def test_rejects_rehashed_library_missing_expected_export(self):
        source = self.root / 'forged.cpp'
        source.write_text('extern "C" int recovered_2000(){return 7;}')
        subprocess.run(['g++','-shared','-fPIC',str(source),'-o',
                        str(self.bundle / 'recovered_candidates.so')], check=True)
        self._rehash_library()
        with self.assertRaisesRegex(ValueError, 'native ELF export mismatch'):
            verify(self.bundle)

    def test_rejects_rehashed_non_elf_library(self):
        (self.bundle / 'recovered_candidates.so').write_bytes(b'not a shared library')
        self._rehash_library()
        with self.assertRaisesRegex(ValueError, 'native library is invalid'):
            verify(self.bundle)

    def test_rejects_rehashed_library_with_extra_export(self):
        source = self.root / 'forged.cpp'
        source.write_text('extern "C" int recovered_2000(){return 7;} '
                          'extern "C" int recovered_3000(){return 7;} '
                          'extern "C" int recovered_dead(){return 0;}')
        subprocess.run(['g++','-shared','-fPIC',str(source),'-o',
                        str(self.bundle / 'recovered_candidates.so')], check=True)
        self._rehash_library()
        with self.assertRaisesRegex(ValueError, 'native ELF export mismatch'):
            verify(self.bundle)

    def test_rejects_unresolved_recovered_dependency(self):
        source = self.root / 'forged.cpp'
        source.write_text('extern "C" int recovered_4040(); '
                          'extern "C" int recovered_2000(){return recovered_4040();} '
                          'extern "C" int recovered_3000(){return 1;}')
        subprocess.run(['g++','-shared','-fPIC',str(source),'-o',
                        str(self.bundle / 'recovered_candidates.so')], check=True)
        self._rehash_library()
        with self.assertRaisesRegex(ValueError, 'native ELF export mismatch'):
            verify(self.bundle)

    def test_rejects_modified_cpp(self):
        with (self.bundle / 'candidate_2000.cpp').open('a') as f:
            f.write('// unexpected edit\n')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            verify(self.bundle)

    def test_rejects_modified_coverage(self):
        p = self.bundle / 'coverage.json'
        p.write_text(p.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            verify(self.bundle)

    def test_rejects_modified_shared_library(self):
        with (self.bundle / 'recovered_candidates.so').open('ab') as f:
            f.write(b'INJECTED')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            verify(self.bundle)

    def test_rejects_missing_candidate(self):
        (self.bundle / 'candidate_3000.cpp').unlink()
        with self.assertRaisesRegex(ValueError, 'candidate count'):
            verify(self.bundle)

    def test_rejects_untracked_candidate(self):
        (self.bundle / 'candidate_4000.cpp').write_text('int unused;')
        with self.assertRaisesRegex(ValueError, 'candidate count'):
            verify(self.bundle)

    def test_rejects_symlinked_candidate(self):
        p = self.bundle / 'candidate_2000.cpp'
        p.rename(self.bundle / 'hidden.cpp')
        p.symlink_to('hidden.cpp')
        with self.assertRaisesRegex(ValueError, 'symlinked'):
            verify(self.bundle)

    def test_rejects_other_original_elf(self):
        other = self.root / 'other.elf'
        other.write_bytes(b'different')
        with self.assertRaisesRegex(ValueError, 'ELF digest mismatch'):
            verify(self.bundle, other)

    def test_rejects_forged_native_report_even_if_rehashed(self):
        p = self.bundle / 'native_link.json'
        report = json.loads(p.read_text())
        report['candidates'][0]['export_defined'] = False
        p.write_text(json.dumps(report))
        manifest_path = self.bundle / 'bundle_manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['files'][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'native export evidence'):
            verify(self.bundle)

    def test_rejects_forged_coverage_even_if_rehashed(self):
        p = self.bundle / 'coverage.json'
        coverage = json.loads(p.read_text())
        coverage['source_read'] = True
        p.write_text(json.dumps(coverage))
        manifest_path = self.bundle / 'bundle_manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['files'][p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'coverage provenance'):
            verify(self.bundle)


if __name__ == '__main__':
    unittest.main()
