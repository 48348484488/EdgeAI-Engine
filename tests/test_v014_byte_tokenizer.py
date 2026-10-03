import sys,unittest
from pathlib import Path
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'benchmarks'))

from byte_bpe import ByteBPE
from transformer_model import TinyTransformer
import instruction_byte_v014 as v14

class ByteTokenizerV014Tests(unittest.TestCase):
    def test_remap_preserves_byte_and_special_logits(self):
        torch.manual_seed(123)
        old_tok=ByteBPE(((65,66),),instruction=True)
        model=TinyTransformer(dim=8,hidden=12,window=8,precision='fp32',
                              vocab_size=old_tok.vocab_size,blocks=2).eval()
        new_model,new_tok=v14.remap_to_byte_model(model,old_tok)
        self.assertEqual(new_tok.merges,())
        self.assertTrue(new_tok.instruction)
        self.assertEqual(new_model.vocab_size,259)

        old_ids=torch.tensor([[old_tok.bos_id,65,66,old_tok.response_id]],dtype=torch.long)
        new_ids=torch.tensor([[new_tok.bos_id,65,66,new_tok.response_id]],dtype=torch.long)
        old_logits=model(old_ids)
        new_logits=new_model(new_ids)
        keep=list(range(256))+[old_tok.bos_id,old_tok.response_id,old_tok.eos_id]
        torch.testing.assert_close(new_logits,old_logits[...,keep],rtol=0,atol=0)

    def test_remap_does_not_mutate_source(self):
        torch.manual_seed(456)
        tok=ByteBPE(((97,98),),instruction=True)
        model=TinyTransformer(dim=8,hidden=12,window=8,precision='fp32',
                              vocab_size=tok.vocab_size,blocks=1).eval()
        before={k:v.detach().clone() for k,v in model.state_dict().items()}
        v14.remap_to_byte_model(model,tok)
        for k,v in before.items():
            torch.testing.assert_close(model.state_dict()[k],v,rtol=0,atol=0)

if __name__=='__main__':
    unittest.main()
