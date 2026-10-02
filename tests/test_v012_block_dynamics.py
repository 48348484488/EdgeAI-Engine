import sys,unittest
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'));sys.path.insert(0,str(ROOT/'tools'))
import v012_block_dynamics as d
from transformer_model import TinyTransformer

class V012BlockDynamicsTests(unittest.TestCase):
    def test_group_name_separates_new_block_output_and_inner(self):
        self.assertEqual(d.group_name('blocks.0.query.weight'),'block0')
        self.assertEqual(d.group_name('blocks.1.project.weight'),'block1_output')
        self.assertEqual(d.group_name('blocks.1.down.bias'),'block1_output')
        self.assertEqual(d.group_name('blocks.1.query.weight'),'block1_inner')
        self.assertEqual(d.group_name('emb.weight'),'shared')

    def test_zero_output_projection_blocks_inner_gradient_on_first_step(self):
        torch.manual_seed(7)
        m=TinyTransformer(dim=8,hidden=12,window=4,precision='fp32',vocab_size=256,blocks=2)
        with torch.no_grad():
            m.blocks[1].project.weight.zero_();m.blocks[1].project.bias.zero_()
            m.blocks[1].down.weight.zero_();m.blocks[1].down.bias.zero_()
        x=torch.tensor([[1,2,3]],dtype=torch.long);loss=m(x).square().mean();loss.backward()
        g=d.grad_norms(m)
        self.assertGreater(g['block1_output'],0.0)
        self.assertEqual(g['block1_inner'],0.0)

if __name__=='__main__':unittest.main()
