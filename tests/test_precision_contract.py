"""Contracts for selective precision; all tests inspect real model behavior."""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import torch
from torch.nn import functional as F
try:
    from mixed_model import MixedHybrid, Int8Linear, POLICIES, export_mixed
except ImportError:
    MixedHybrid = None

class PrecisionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1)
    def setUp(self):
        self.assertIsNotNone(MixedHybrid, 'mixed precision implementation is missing')
    def test_policies_keep_same_master_parameters(self):
        baseline = None
        for policy in POLICIES:
            torch.manual_seed(29)
            model = MixedHybrid(16, 32, 8, 7, 2, policy=policy)
            weights = model.state_dict()
            if baseline is None:
                baseline = weights
            for key in weights:
                torch.testing.assert_close(weights[key], baseline[key], rtol=0, atol=0)
    def test_int8_grid_and_zero_rows(self):
        layer = Int8Linear(5, 3)
        with torch.no_grad():
            layer.weight.copy_(torch.tensor([[0.,0,0,0,0],[-1.,-.333,0,.6,1.],[.001,.002,.004,-.003,0.]]))
        scale = layer.weight.detach().abs().amax(1, keepdim=True).clamp_min(1e-8)/127
        expected = (layer.weight.detach()/scale).round().clamp(-127,127)*scale
        torch.testing.assert_close(layer.effective(), expected, rtol=1e-6, atol=1e-7)
        self.assertTrue(torch.isfinite(layer.effective()).all())
        layer(torch.ones(2,5)).sum().backward()
        torch.testing.assert_close(layer.weight.grad, torch.full_like(layer.weight, 2))
    def test_causal_and_all_parameters_train(self):
        for policy in POLICIES:
            with self.subTest(policy=policy):
                torch.manual_seed(77)
                model = MixedHybrid(12,20,5,4,2,policy=policy)
                tokens = torch.randint(0,256,(2,14))
                z = model(tokens)
                torch.testing.assert_close(z[:,:5], model(tokens[:,:5]), rtol=3e-5, atol=3e-5)
                F.cross_entropy(z.flatten(0,1), torch.randint(0,256,(28,))).backward()
                for name, p in model.named_parameters():
                    self.assertIsNotNone(p.grad, name)
                    self.assertTrue(torch.isfinite(p.grad).all(), name)
                    self.assertGreater(p.grad.abs().sum().item(), 0, name)
    def test_fp32_is_unchanged_reference(self):
        from hybrid_model import HybridTiny
        torch.manual_seed(19); reference=HybridTiny(16,32,8,8,1,ternary=False)
        torch.manual_seed(19); mixed=MixedHybrid(16,32,8,8,1,policy='fp32')
        x=torch.randint(0,256,(3,20))
        torch.testing.assert_close(mixed(x),reference(x),rtol=0,atol=0)
    def test_export_validates_and_is_atomic(self):
        model=MixedHybrid(16,32,8,8,1,policy='memory_int8')
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'mixed.edge'
            export_mixed(model,path)
            previous=path.read_bytes()
            self.assertEqual(previous[:8], b'EDGEAI4\0')
            with torch.no_grad():model.emb.weight[0,0]=float('nan')
            with self.assertRaises(ValueError):export_mixed(model,path)
            self.assertEqual(path.read_bytes(),previous)
    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):MixedHybrid(policy='fp4-magic')
        with self.assertRaises(ValueError):MixedHybrid(output_precision='invalid')

if __name__=='__main__':unittest.main()
