"""Recovery contract; tests use real ZIPs and temporary directories."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

FILE = Path(__file__).resolve().parents[1] / 'tools' / 'release_bundle.py'
if FILE.exists():
    spec = importlib.util.spec_from_file_location('release_bundle', FILE)
    bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundle)
else:
    bundle = None

class ReleaseBundleTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(bundle, 'release_bundle.py has not been implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'Project'
        (self.source / 'models').mkdir(parents=True)
        (self.source / 'README.md').write_text('olá\n', encoding='utf-8')
        (self.source / 'models' / 'tiny.edge').write_bytes(bytes(range(256)))
        self.archive = self.root / 'release.zip'

    def pack(self):
        return bundle.pack(self.source, self.archive)

    def rewrite(self, change):
        with zipfile.ZipFile(self.archive) as z:
            entries = [(info, z.read(info)) for info in z.infolist()]
        with zipfile.ZipFile(self.archive, 'w') as z:
            for info, value in entries:
                z.writestr(info, change(info.filename, value))

    def test_real_roundtrip_and_hashes(self):
        result = self.pack()
        self.assertEqual(result['files'], 2)
        self.assertEqual(result['sha256'], bundle.sha256_file(self.archive))
        bundle.verify(self.archive)
        output = self.root / 'restored'
        bundle.unpack(self.archive, output)
        self.assertEqual((output / 'models/tiny.edge').read_bytes(), bytes(range(256)))
        self.assertEqual((output / 'README.md').read_text(), 'olá\n')

    def test_modification_detected_even_with_valid_zip_crc(self):
        self.pack()
        self.rewrite(lambda n, b: b'evil' if n.endswith('tiny.edge') else b)
        with self.assertRaisesRegex(ValueError, 'integrity'):
            bundle.verify(self.archive)
        with self.assertRaises(ValueError):
            bundle.unpack(self.archive, self.root / 'bad')
        self.assertFalse((self.root / 'bad').exists())

    def test_unlisted_extra_file_rejected(self):
        self.pack()
        with zipfile.ZipFile(self.archive, 'a') as z:
            z.writestr('Project/extra.txt', b'not in manifest')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            bundle.verify(self.archive)

    def test_zip_traversal_rejected(self):
        self.pack()
        with zipfile.ZipFile(self.archive, 'a') as z:
            z.writestr('../outside.txt', b'bad')
        with self.assertRaises(ValueError):
            bundle.unpack(self.archive, self.root / 'restored')
        self.assertFalse((self.root / 'outside.txt').exists())

    def test_existing_archive_not_overwritten_by_default(self):
        self.archive.write_bytes(b'prior backup')
        with self.assertRaises(FileExistsError):
            self.pack()
        self.assertEqual(self.archive.read_bytes(), b'prior backup')

    def test_failed_verification_preserves_previous_release(self):
        self.pack()
        old = self.archive.read_bytes()
        (self.source / 'README.md').write_text('new')
        # Failure injection at verification gate; all ZIP I/O is real.
        with patch.object(bundle, 'verify', side_effect=ValueError('injected failure')):
            with self.assertRaises(ValueError):
                bundle.pack(self.source, self.archive, replace=True)
        self.assertEqual(self.archive.read_bytes(), old)
        self.assertFalse(list(self.root.glob('*.partial')))

    def test_successful_replace_and_exclusions(self):
        self.pack()
        for d in ['build', 'build-portable', '__pycache__', '.git']:
            (self.source / d).mkdir()
            (self.source / d / 'scratch').write_bytes(b'not for distribution')
        (self.source / 'README.md').write_text('changed')
        result = bundle.pack(self.source, self.archive, replace=True)
        self.assertEqual(result['files'], 2)
        with zipfile.ZipFile(self.archive) as z:
            self.assertEqual(z.read('Project/README.md'), b'changed')

    def test_existing_unpack_directory_not_touched(self):
        self.pack()
        dest = self.root / 'existing'; dest.mkdir()
        (dest / 'keep').write_text('safe')
        with self.assertRaises(FileExistsError):
            bundle.unpack(self.archive, dest)
        self.assertEqual((dest / 'keep').read_text(), 'safe')

    @unittest.skipIf(os.name == 'nt', 'requires Unix symbolic links')
    def test_symlinks_are_not_followed(self):
        (self.source / 'secret').symlink_to(self.root / 'external')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.pack()
        self.assertFalse(self.archive.exists())

    @unittest.skipIf(os.name == 'nt', 'Unix permission contract')
    def test_executable_bit_preserved(self):
        executable = self.source / 'run.sh'; executable.write_text('#!/bin/sh\nexit 0\n')
        executable.chmod(0o755)
        self.pack(); dest = self.root / 'restored'; bundle.unpack(self.archive, dest)
        self.assertTrue(os.access(dest / 'run.sh', os.X_OK))

    def test_size_limit_enforced(self):
        self.pack()
        with self.assertRaisesRegex(ValueError, 'size limit'):
            bundle.verify(self.archive, max_bytes=20)

    def test_archive_cannot_be_inside_source(self):
        with self.assertRaises(ValueError):
            bundle.pack(self.source, self.source / 'self.zip')

    def test_truncated_archive_rejected(self):
        self.pack(); self.archive.write_bytes(self.archive.read_bytes()[:32])
        with self.assertRaises(ValueError):
            bundle.verify(self.archive)

    def test_repeated_snapshot_is_deterministic(self):
        self.pack()
        other = self.root / 'other.zip'
        bundle.pack(self.source, other)
        self.assertEqual(self.archive.read_bytes(), other.read_bytes())

if __name__ == '__main__':
    unittest.main()
