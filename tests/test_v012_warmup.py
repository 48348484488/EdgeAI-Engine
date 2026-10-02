import sys,unittest
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'));sys.path.insert(0,str(ROOT/'tools'))
import instruction_blocks_warmup_v012 as warm
from transformer_model import TinyTransformer

class V012WarmupTests(unittest.TestCase):
    def make_model(self):
        torch.manual_seed(7)
        return TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',blocks=2)

    def test_new_block_phase_freezes_inherited_parameters(self):
        m=self.make_model();warm.set_train_phase(m,'new_block')
        self.assertFalse(any(p.requires_grad for p in m.emb.parameters()))
        self.assertFalse(any(p.requires_grad for p in m.blocks[0].parameters()))
        self.assertFalse(any(p.requires_grad for p in m.out.parameters()))
        self.assertTrue(all(p.requires_grad for p in m.blocks[1].parameters()))

    def test_all_phase_unfreezes_everything(self):
        m=self.make_model();warm.set_train_phase(m,'new_block');warm.set_train_phase(m,'all')
        self.assertTrue(all(p.requires_grad for p in m.parameters()))

    def test_gradient_snapshot_separates_new_inner_and_output_paths(self):
        m=self.make_model()
        with torch.no_grad():
            for name in ('project','down'):
                layer=getattr(m.blocks[1],name);layer.weight.zero_();layer.bias.zero_()
        warm.set_train_phase(m,'all')
        x=torch.tensor([[1,2,3,4]],dtype=torch.long)
        m(x).sum().backward()
        s=warm.gradient_snapshot(m)
        self.assertGreater(s['new_output_grad_l2'],0.0)
        self.assertEqual(s['new_inner_grad_l2'],0.0)

    def test_rejects_non_two_block_model(self):
        m=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',blocks=1)
        with self.assertRaises(ValueError): warm.set_train_phase(m,'new_block')

if __name__=='__main__': unittest.main()
