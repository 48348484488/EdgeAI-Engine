import importlib.util
import inspect
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from transformer_model import TinyTransformer
class FeatureGate(unittest.TestCase):
    def test_native_tokenizer_reference_exists(self):
        self.assertIsNotNone(importlib.util.find_spec('byte_bpe'),'reversible BPE is missing')
    def test_transformer_accepts_dynamic_vocabulary(self):
        self.assertIn('vocab_size',inspect.signature(TinyTransformer).parameters)
if __name__=='__main__':unittest.main()

from byte_bpe import ByteBPE
import tempfile
import torch
from transformer_model import export_transformer
class BPEContract(unittest.TestCase):
    def test_lossless_every_byte_and_utf8(self):
        t=ByteBPE.train([b'banana banana banana aaa aaa', 'ação, café, 🐈'.encode()],280)
        for raw in (b'',bytes(range(256))*3,'ação, café, 🐈\n'.encode(),b'\0\xff\n\t'):
            self.assertEqual(t.decode(t.encode(raw,add_bos=True)),raw)
    def test_rank_and_nonoverlapping_repeats(self):
        t=ByteBPE([(97,97),(256,256)])
        self.assertEqual(t.encode(b'aaaaa'),[257,97])
        self.assertEqual(t.encode(b'aa aa\naa'),[256,32,256,10,256])
    def test_strict_invalid_merges_and_ids(self):
        for pairs in ([(256,1)],[(97,98),(97,98)],[(97,32)],[(10,10)],[(True,2)],[(97,98),(98,99),(256,99),(97,257)]):
            with self.assertRaises(ValueError):ByteBPE(pairs)
        for ids in ([-1],[257],[False]):
            with self.assertRaises(ValueError):ByteBPE().decode(ids)
    def test_deterministic_train_and_json(self):
        docs=[b'alpha alpha beta beta delta',b'alpha beta alpha']
        a=ByteBPE.train(docs,275);b=ByteBPE.train(docs[::-1],275)
        self.assertEqual(a.fingerprint(),b.fingerprint())
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'t.json';a.save(p);self.assertEqual(a.payload(),ByteBPE.load(p).payload())
    def test_bos_and_vocabulary(self):
        self.assertEqual(ByteBPE().bos_id,256)
        self.assertEqual(ByteBPE().encode(b'',True),[256])
        for v in (0,255,4097):
            with self.assertRaises(ValueError):TinyTransformer(vocab_size=v)
    def test_variable_model_shapes_gradients_and_causality(self):
        torch.manual_seed(7);m=TinyTransformer(dim=16,hidden=23,window=5,vocab_size=513)
        x=torch.randint(0,513,(2,12));z=m(x);self.assertEqual(tuple(z.shape),(2,12,513))
        other=x.clone();other[:,7:]=(other[:,7:]+1)%513
        self.assertTrue(torch.equal(z[:,:7],m(other)[:,:7]))
        z.sum().backward()
        for p in m.parameters():self.assertIsNotNone(p.grad);self.assertTrue(torch.isfinite(p.grad).all())
    def test_export_requires_matching_tokenizer(self):
        m=TinyTransformer(dim=8,hidden=9,vocab_size=257)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'m.edge'
            with self.assertRaises(ValueError):export_transformer(m,p)
            with self.assertRaises(ValueError):export_transformer(m,p,tokenizer=ByteBPE([(97,98)]))
            export_transformer(m,p,tokenizer=ByteBPE());self.assertEqual(p.read_bytes()[:8],b'EDGEAI6\0')
