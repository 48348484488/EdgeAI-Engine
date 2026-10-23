"""Offline CI runner fail-closed integrity regressions; no network required."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from edgeai_offline_ci import exact_file,safe_unpack,require

class OfflineGuardTests(unittest.TestCase):
    def test_exact_binary_hash_rejects_edit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'target';p.write_bytes(b'abc')
            expected=hashlib.sha256(b'abc').hexdigest()
            exact_file(p,expected)
            p.write_bytes(b'abd')
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                exact_file(p,expected)

    def test_missing_binary_fails(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'missing'):
                exact_file(Path(d)/'nothing','0'*64)

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            archive=Path(d)/'malicious.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('../escape.txt',b'malicious')
            with self.assertRaisesRegex(ValueError,'unsafe ZIP'):
                safe_unpack(archive,Path(d)/'extracted')
            self.assertFalse((Path(d)/'escape.txt').exists())

    def test_oversized_expansion_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            archive=Path(d)/'huge.zip'
            with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('huge',b'Z'*1024)
            with self.assertRaisesRegex(ValueError,'budget'):
                safe_unpack(archive,Path(d)/'x',max_bytes=512)

    def test_symlink_zip_entry_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            archive=Path(d)/'symlink.zip'
            with zipfile.ZipFile(archive,'w') as z:
                entry=zipfile.ZipInfo('link')
                entry.create_system=3
                entry.external_attr=(0o120777<<16)
                z.writestr(entry,'../../secret')
            with self.assertRaisesRegex(ValueError,'unsafe ZIP'):
                safe_unpack(archive,Path(d)/'target')

    def test_nonoptimizable_guards(self):
        with self.assertRaisesRegex(ValueError,'closed'):
            require(False,'closed')

if __name__=='__main__':unittest.main()
