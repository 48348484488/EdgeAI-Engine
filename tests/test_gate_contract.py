import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import torch
from hybrid_model import HybridTiny
class GateContract(unittest.TestCase):
    def test_input_dependent_gates_are_trainable(self):
        model=HybridTiny(16,32,8,8,1)
        self.assertTrue(hasattr(model,"gates"),"No input-dependent gate projection")
        x=torch.randint(0,256,(2,16));model(x).square().mean().backward()
        self.assertIsNotNone(model.gates.weight.grad)
        self.assertGreater(model.gates.weight.grad.abs().sum().item(),0)
if __name__=="__main__":unittest.main()
