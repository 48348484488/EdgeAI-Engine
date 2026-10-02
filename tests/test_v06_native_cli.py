import json,math,os,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BUILD=Path(os.environ.get('EDGEAI_BUILD_DIR',str(ROOT/'build')))
sys.path.insert(0,str(ROOT/'tools'))
import torch
from byte_bpe import ByteBPE
from transformer_model import TinyTransformer,export_transformer
from external_data import write_blocks
class NativeCLIContract(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1);self.temp=tempfile.TemporaryDirectory();self.d=Path(self.temp.name);self.tok=ByteBPE([(97,97)])
        model=TinyTransformer(dim=8,hidden=9,vocab_size=self.tok.vocab_size)
        with torch.no_grad():
            for p in model.parameters():p.zero_()
        self.model=self.d/'m.edge';export_transformer(model,self.model,tokenizer=self.tok)
    def tearDown(self):self.temp.cleanup()
    def test_native_ids_include_bos_and_raw_bytes_survive(self):
        p=self.d/'raw';p.write_bytes(b'aaaaa\0\xff')
        r=json.loads(subprocess.check_output([str(BUILD/'edgeai_tokenize'),str(self.model),str(p)],text=True))
        self.assertEqual(r['ids'],[257,256,256,97,0,255]);self.assertEqual(r['raw_bytes'],7)
    def test_native_bpb_denominator_and_reset(self):
        p=self.d/'blocks';write_blocks(p,[b'aaaa',b'a'])
        r=json.loads(subprocess.check_output([str(BUILD/'edgeai_text_eval'),str(self.model),str(p)],text=True))
        self.assertEqual(r['raw_bytes'],5);self.assertEqual(r['target_tokens'],3);self.assertFalse(r['bos_scored_as_byte'])
        self.assertAlmostEqual(r['bits_per_byte'],3*math.log2(258)/5,places=7)
    def test_native_rejects_truncated_and_trailing_blocks(self):
        p=self.d/'blocks'
        for raw in (b'',b'EDGRAW1\0'+struct.pack('<II',1,400)+b'x',b'EDGRAW1\0'+struct.pack('<II',1,1)+b'ab'):
            p.write_bytes(raw);r=subprocess.run([str(BUILD/'edgeai_text_eval'),str(self.model),str(p)],capture_output=True)
            self.assertNotEqual(r.returncode,0)
    def test_generation_invalid_limits_rejected(self):
        p=self.d/'prompt';p.write_bytes(b'hello')
        for n in ('0','-1','4097','nan','2x'):
            r=subprocess.run([str(BUILD/'edgeai_generate'),str(self.model),str(p),str(self.d/'out'),n],capture_output=True);self.assertNotEqual(r.returncode,0)
    def test_legacy_metric_refuses_dynamic_tokenization(self):
        p=self.d/'blocks';p.write_bytes(b'EDGBLK1\0'+struct.pack('<II',1,1)+b'ab')
        r=subprocess.run([str(BUILD/'edgeai_evaluate'),str(self.model),str(p)],capture_output=True)
        self.assertNotEqual(r.returncode,0);self.assertIn(b'edgeai_text_eval',r.stderr)
if __name__=='__main__':unittest.main()
