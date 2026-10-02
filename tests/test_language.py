"""Regression contracts written before the v0.5 implementation."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import torch
class LanguageTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
    def module(self,name):
        self.assertIsNotNone(importlib.util.find_spec(name),f'{name} must be implemented')
        return __import__(name)
    def test_causal_prefix_no_future_leakage(self):
        M=self.module('transformer_model').TinyTransformer
        for policy in ('fp32','int8','ternary'):
            torch.manual_seed(7);m=M(dim=16,hidden=25,window=5,precision=policy)
            x=torch.randint(0,256,(2,17));y=x.clone();y[:,9:]=0
            with torch.no_grad():
                torch.testing.assert_close(m(x)[:,:9],m(y)[:,:9],atol=2e-6,rtol=2e-6)
    def test_invalid_config(self):
        M=self.module('transformer_model').TinyTransformer
        for kwargs in ({'dim':7},{'window':0},{'precision':'invalid'},{'hidden':0}):
            with self.assertRaises(ValueError):M(**kwargs)
    def test_same_master_initialization(self):
        M=self.module('transformer_model').TinyTransformer
        torch.manual_seed(19);a=M(dim=16,hidden=25,precision='fp32')
        torch.manual_seed(19);b=M(dim=16,hidden=25,precision='int8')
        for name,w in a.state_dict().items():torch.testing.assert_close(w,b.state_dict()[name],atol=0,rtol=0)
    def test_gradients_reach_all_parameters(self):
        M=self.module('transformer_model').TinyTransformer
        m=M(dim=16,hidden=24,precision='int8')
        m(torch.randint(0,256,(2,9))).square().mean().backward()
        for name,p in m.named_parameters():
            self.assertIsNotNone(p.grad,name);self.assertTrue(torch.isfinite(p.grad).all(),name)
    def test_export_rejects_nonfinite_and_preserves_file(self):
        mod=self.module('transformer_model');m=mod.TinyTransformer(dim=8,hidden=9)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'m.edge';path.write_bytes(b'original')
            with torch.no_grad():m.out.weight[0,0]=float('nan')
            with self.assertRaises(ValueError):mod.export_transformer(m,path)
            self.assertEqual(path.read_bytes(),b'original')
    def test_blocks_dont_cross_documents_and_metric_counts(self):
        mod=self.module('language_data')
        docs=[b'abcdef',b'WXYZ123']
        blocks=mod.make_blocks(docs,4)
        self.assertEqual(sum(len(y) for x,y in blocks),11)
        for x,y in blocks:
            raw=bytes(x)+bytes(y[-1:]);self.assertTrue(any(raw in d for d in docs))
        self.assertEqual(mod.bits_per_byte(0.,11),0.)
        with self.assertRaises(ValueError):mod.bits_per_byte(1.,0)
    def test_sampling_reproducible(self):
        mod=self.module('language_data');docs=[bytes(range(70)),bytes(range(40,150))]
        a=mod.sample_batch(docs,4,16,torch.Generator().manual_seed(91))
        b=mod.sample_batch(docs,4,16,torch.Generator().manual_seed(91))
        torch.testing.assert_close(a[0],b[0]);torch.testing.assert_close(a[1],b[1])
        for x,y in zip(*a):self.assertTrue(any(bytes(x.tolist())+bytes(y[-1:].tolist()) in d for d in docs))
    def test_overlap_filter(self):
        mod=self.module('language_data')
        train=[b'abcdefghi'];blocks=mod.make_blocks([b'abcdefghi',b'uvwxyzxyz'],4)
        kept,removed=mod.remove_overlap(blocks,train)
        self.assertEqual(removed,2);self.assertEqual(len(kept),2)
if __name__=='__main__':unittest.main()
