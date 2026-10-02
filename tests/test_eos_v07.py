"""Contracts for native instruction framing, EOS, and legacy preservation."""
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import torch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from byte_bpe import ByteBPE
from transformer_model import TinyTransformer, export_transformer

class EosContract(unittest.TestCase):
    def tok(self):
        self.assertIn('instruction', inspect.signature(ByteBPE).parameters,
                      'tokenizer needs explicit instruction special IDs')
        return ByteBPE([(97,98)], instruction=True)

    def test_distinct_special_ids_after_content(self):
        t=self.tok()
        self.assertEqual((t.bos_id,t.response_id,t.eos_id,t.vocab_size),(257,258,259,260))
        self.assertEqual(t.encode_prompt('ab'),[257,256,258])

    def test_special_ids_never_come_from_text(self):
        t=self.tok();raw=bytes(range(256))+b'<EOS><RESPONSE>'+'ação 😀'.encode()
        ids=t.encode(raw)
        self.assertTrue(all(i<t.bos_id for i in ids))
        self.assertEqual(t.decode([t.bos_id]+ids+[t.response_id,t.eos_id]),raw)

    def test_json_and_legacy_preserved(self):
        t=self.tok()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'t.json';t.save(p)
            self.assertEqual(ByteBPE.load(p).payload(),t.payload())
            old=ByteBPE(t.merges);old.save(p)
            self.assertFalse(ByteBPE.load(p).instruction)
            self.assertEqual(old.payload()['format'],'edge-byte-bpe-1')
            for name in ('response_id','eos_id'):
                with self.assertRaises(ValueError):getattr(old,name)

    def test_native_forced_eos_is_not_a_length_cutoff(self):
        t=self.tok();build=Path(os.getenv('EDGEAI_BUILD_DIR',ROOT/'build'))
        self.assertTrue((build/'edgeai_generate').exists())
        m=TinyTransformer(dim=8,hidden=12,window=8,precision='fp32',vocab_size=t.vocab_size)
        # Deterministic fixture tests runtime only, not learning.
        with torch.no_grad():
            for p in m.parameters():p.zero_()
            m.out.bias[t.bos_id]=100.;m.out.bias[t.response_id]=90.;m.out.bias[t.eos_id]=80.
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);(d/'prompt').write_bytes(b'ab')
            export_transformer(m,d/'m.edge',tokenizer=t,max_generate=32)
            self.assertEqual((d/'m.edge').read_bytes()[:8],b'EDGEAI7\0')
            inspected=subprocess.check_output([str(build/'edgeai_inspect'),str(d/'m.edge')],text=True)
            self.assertIn('format=EDGEAI7',inspected)
            r=subprocess.run([str(build/'edgeai_generate'),str(d/'m.edge'),str(d/'prompt'),str(d/'out'),'8'],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            meta=json.loads(r.stdout)
            self.assertEqual(meta['stop_reason'],'eos');self.assertTrue(meta['stopped_on_eos'])
            self.assertEqual(meta['generated_tokens'],1)
            self.assertEqual(meta['prefill_tokens_including_bos'],3)
            self.assertEqual((d/'out').read_bytes(),b'')
            with torch.no_grad():m.out.bias[ord('x')]=110.
            export_transformer(m,d/'m.edge',tokenizer=t,max_generate=32)
            r=subprocess.run([str(build/'edgeai_generate'),str(d/'m.edge'),str(d/'prompt'),str(d/'out'),'8'],capture_output=True,text=True,check=True)
            meta=json.loads(r.stdout)
            self.assertEqual(meta['stop_reason'],'length');self.assertFalse(meta['stopped_on_eos'])
            self.assertEqual(meta['generated_tokens'],8);self.assertEqual((d/'out').read_bytes(),b'x'*8)

if __name__=='__main__':unittest.main()
