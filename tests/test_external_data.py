import importlib.util
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
class ExternalDataGate(unittest.TestCase):
    def test_external_snapshot_pipeline_present(self):
        self.assertIsNotNone(importlib.util.find_spec('external_data'),'independent data pipeline missing')
if __name__=='__main__':unittest.main()
from external_data import DedupIndex,read_blocks,write_blocks,load_snapshot
import tempfile
class ExternalDataContract(unittest.TestCase):
    def test_normalized_duplicate_detected(self):
        x=DedupIndex();x.add(b'def add(a,b):\n    return a+b','train:0')
        self.assertIsNotNone(x.duplicate(b'def   add ( a, b ) : return a + b'))
        self.assertIsNone(x.duplicate(b'the red fox and the blue river are far apart'))
    def test_near_duplicate_detected(self):
        x=DedupIndex();a=b' '.join(('ident'+str(i)).encode() for i in range(50));x.add(a,'train')
        self.assertIsNotNone(x.duplicate(a.replace(b'ident25',b'renamed')))
    def test_blocks_roundtrip_and_truncation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x';blocks=[bytes(range(256)),b'hello'];write_blocks(p,blocks);self.assertEqual(read_blocks(p),blocks)
            p.write_bytes(p.read_bytes()[:-1])
            with self.assertRaises(ValueError):read_blocks(p)
    def test_snapshot_hash_and_groups(self):
        root=Path(__file__).resolve().parents[1]/'data/cpython_snapshot'
        if not root.exists():self.skipTest('snapshot not built yet')
        m=load_snapshot(root);self.assertEqual(len(m['documents']),18)
        self.assertGreater(m['totals']['train'],59000)
import shutil,json
class SnapshotTamperContract(unittest.TestCase):
    def test_changed_source_rejected(self):
        src=Path(__file__).resolve().parents[1]/'data/cpython_snapshot'
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'snap';shutil.copytree(src,dest);m=json.loads((dest/'manifest.json').read_text());p=dest/m['documents'][0]['path'];p.write_bytes(p.read_bytes()+b'changed')
            with self.assertRaises(ValueError):load_snapshot(dest)
    def test_cross_split_family_rejected(self):
        src=Path(__file__).resolve().parents[1]/'data/cpython_snapshot'
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'snap';shutil.copytree(src,dest);p=dest/'manifest.json';m=json.loads(p.read_text());next(r for r in m['documents'] if r['split']=='test')['family']=m['documents'][0]['family'];p.write_text(json.dumps(m))
            with self.assertRaises(ValueError):load_snapshot(dest)
