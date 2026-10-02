"""Real masking, splits, checkpoint expansion, and restricted scoring contracts."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))

class SFTContract(unittest.TestCase):
    def modules(self):
        self.assertIsNotNone(importlib.util.find_spec('instruction_data'),'missing frozen synthetic instruction corpus')
        self.assertIsNotNone(importlib.util.find_spec('sft_model'),'missing response-only trainer helpers')
        import instruction_data as data
        import sft_model as sft
        return data,sft

    def test_splits_deterministic_disjoint_and_heldout(self):
        data,_=self.modules();a=data.build_dataset();b=data.build_dataset()
        self.assertEqual(a,b)
        data.validate_dataset(a)
        groups={name:{r['group'] for r in rows} for name,rows in a.items()}
        for x in groups:
            for y in groups:
                if x!=y:self.assertFalse(groups[x]&groups[y],(x,y))
        seen_templates={r['template'] for r in a['train']}
        self.assertFalse(seen_templates & {r['template'] for r in a['test_template']})
        self.assertFalse({r['task'] for r in a['train']} & {r['task'] for r in a['test_family']})

    def test_hash_integrity_and_no_test_rows_in_train(self):
        data,_=self.modules()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);data.write_dataset(root);data.load_dataset(root)
            p=root/'train.jsonl';p.write_bytes(p.read_bytes()+b'\n')
            with self.assertRaises(ValueError):data.load_dataset(root)
        rows=data.build_dataset();rows['train'].append(rows['test_id'][0])
        with self.assertRaises(ValueError):data.validate_dataset(rows)

    def test_response_targets_shift_once_include_eos_and_ignore_prompt(self):
        _,sft=self.modules()
        from byte_bpe import ByteBPE
        tok=ByteBPE(instruction=True)
        rows=[dict(prompt='a',answer='xy'),dict(prompt='abcd',answer='z')]
        x,y=sft.make_batch(rows,tok,max_length=32)
        n=len(tok.encode_prompt('a'))
        self.assertEqual(y[0,:n-1].tolist(),[-100]*(n-1))
        self.assertEqual(y[0,n-1:n+2].tolist(),[ord('x'),ord('y'),tok.eos_id])
        self.assertEqual(x[0,n-1].item(),tok.response_id)
        self.assertTrue(torch.all(y[0,n+2:]==-100))
        with self.assertRaises(ValueError):sft.make_batch(rows,tok,max_length=3)
        # Prompt and padding logits cannot affect loss or their gradients.
        logits=torch.randn(*y.shape,tok.vocab_size,requires_grad=True)
        loss=sft.response_loss(logits,y);loss.backward()
        self.assertTrue(torch.all(logits.grad[y==-100]==0))
        with self.assertRaises(ValueError):sft.response_loss(logits,torch.full_like(y,-100))

    def test_warmstart_preserves_old_logits(self):
        _,sft=self.modules()
        from byte_bpe import ByteBPE
        from transformer_model import TinyTransformer
        torch.manual_seed(99);old=TinyTransformer(dim=8,hidden=12,vocab_size=257)
        cp=dict(config=old.export_config(),state_dict=old.state_dict(),tokenizer=ByteBPE().payload())
        model,tok=sft.expand_checkpoint(cp,seed=1)
        ids=torch.tensor([[256,65,66]])
        with torch.inference_mode():
            self.assertTrue(torch.allclose(old(ids),model(ids)[...,:257],atol=1e-6))
        self.assertEqual(model.vocab_size,259);self.assertTrue(tok.instruction)

    def test_no_execution_in_expression_scoring(self):
        data,_=self.modules()
        row=dict(task='expression',answer='x+3')
        self.assertTrue(data.score(row,b'3+x'))
        self.assertFalse(data.score(row,b'x+4'))
        for value in (b'__import__("os").system("true")',b'x**9999999',b'x/0',b'x+3\nextra'):
            self.assertFalse(data.score(row,value))
        self.assertFalse(data.score(dict(task='copy',answer='ab'),b'ab '))
        self.assertTrue(data.score(dict(task='copy',answer='ab'),b'ab'))

if __name__=='__main__':unittest.main()
