import importlib.util,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
class TrainingGate(unittest.TestCase):
    def test_external_tokenization_comparison_present(self):
        self.assertIsNotNone(importlib.util.find_spec('tokenization_v06'))
if __name__=='__main__':unittest.main()
from tokenization_v06 import evaluate,sample_batch,cached_ok
from byte_bpe import ByteBPE
from transformer_model import TinyTransformer
import torch,random,math
class TrainingMetricContract(unittest.TestCase):
    def test_every_byte_scored_bos_is_not_byte(self):
        torch.set_num_threads(1);tok=ByteBPE([(97,97)]);model=TinyTransformer(dim=8,hidden=9,vocab_size=tok.vocab_size)
        with torch.no_grad():
            for p in model.parameters():p.zero_()
        metrics=evaluate(model,[b'aaaa',b'a'],tok)
        self.assertEqual(metrics['raw_bytes'],5);self.assertEqual(metrics['target_tokens'],3)
        self.assertAlmostEqual(metrics['bits_per_byte'],3*math.log2(tok.vocab_size)/5,places=5)
    def test_sampler_targets_exclude_bos(self):
        tok=ByteBPE();x,y=sample_batch([list(b'abc '*50)],[200],tok,random.Random(7),batch=2,seq=16)
        self.assertTrue((x[:,0]==tok.bos_id).all());self.assertTrue((y!=tok.bos_id).all());self.assertTrue(torch.equal(x[:,1:],y[:,:-1]))
    def test_cache_rejects_missing_artifacts_or_identity(self):
        self.assertFalse(cached_ok({'identity':{'a':1}}, {'a':1}))
        self.assertFalse(cached_ok({'identity':{'a':1},'artifacts':{}},{'a':2}))
from tokenization_v06 import identity
class TrainingCacheHostContract(unittest.TestCase):
    def test_training_identity_includes_host(self):
        root=Path(__file__).resolve().parents[1]
        key=identity('byte257',11,20.,1,root/'data/cpython_snapshot/manifest.json',ByteBPE())
        self.assertIn('host',key,'cached training time must not be silently attributed to a different CPU')
class CheckpointSafeMetadataContract(unittest.TestCase):
    def test_identity_version_is_plain_string_for_weights_only_load(self):
        import io
        root=Path(__file__).resolve().parents[1]
        key=identity('byte257',11,20.,1,root/'data/cpython_snapshot/manifest.json',ByteBPE())
        self.assertIs(type(key['torch']),str,'TorchVersion pickles a class rejected by weights_only=True')
        buffer=io.BytesIO();torch.save({'identity':key,'state_dict':{'weight':torch.zeros(1)}},buffer);buffer.seek(0)
        self.assertEqual(torch.load(buffer,weights_only=True)['identity'],key)
