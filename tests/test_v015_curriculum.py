import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import build_dataset
from instruction_data_v015 import build_v015

class V015CurriculumTests(unittest.TestCase):
    def setUp(self):
        self.old=build_dataset();self.new=build_v015()

    def test_shared_sealed_splits_unchanged(self):
        for split in ('valid','test_id','test_template','test_family'):
            self.assertEqual(self.new[split],self.old[split])

    def test_training_boundary_is_expanded(self):
        train=self.new['train']
        self.assertTrue(any(r['task']=='copy' and len(r['answer'])==6 for r in train))
        self.assertTrue(any(r['task']=='addition' and '39' in r['prompt'] for r in train))
        self.assertTrue(any(r['task']=='expression' and '49' in r['answer'] for r in train))

    def test_new_range_is_beyond_training_and_disjoint(self):
        train=self.new['train'];hold=self.new['test_range']
        self.assertEqual(len(hold),128)
        self.assertFalse({r['group'] for r in train}&{r['group'] for r in hold})
        self.assertFalse({r['prompt'] for r in train}&{r['prompt'] for r in hold})
        for r in hold:
            if r['task'] in ('copy','uppercase'):
                self.assertEqual(len(r['answer']),7)
            elif r['task']=='addition':
                nums=[int(x) for x in r['prompt'].replace('?','').replace('+',' ').split() if x.isdigit()]
                self.assertTrue(all(40<=n<=49 for n in nums))
            elif r['task']=='expression':
                k=int(''.join(ch for ch in r['answer'] if ch.isdigit()))
                self.assertTrue(50<=k<=59)

if __name__=='__main__':unittest.main()
