import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import instruction_data_v013_length as length

class LengthBridgeV013Tests(unittest.TestCase):
    def test_adds_exactly_512_length5_groups(self):
        d=length.build_v013_length()
        rows=[r for r in d['train'] if r['group'].startswith('v013len5:')]
        self.assertEqual(len(rows),length.LENGTH5_STRINGS*4)
        self.assertEqual(len({r['group'] for r in rows}),length.LENGTH5_STRINGS)
        self.assertTrue(all(len(r['group'].split(':',1)[1])==5 for r in rows))

    def test_length6_remains_unseen_in_training(self):
        d=length.build_v013_length()
        bridge=[r for r in d['train'] if r['task'] in ('copy','uppercase')]
        self.assertFalse(any(len(r['answer'].lower())==6 for r in bridge))

    def test_all_sealed_splits_remain_byte_identical(self):
        d=length.build_v013_length()
        for split in ('valid','test_id','test_template','test_range','test_family'):
            generated=('\n'.join(length.dumps(r) for r in d[split])+'\n').encode()
            original=(ROOT/'data/instructions_v07'/f'{split}.jsonl').read_bytes()
            self.assertEqual(generated,original)

    def test_no_sealed_prompt_answer_enters_training(self):
        d=length.build_v013_length();train={(r['prompt'],r['answer']) for r in d['train']}
        for split in ('test_id','test_template','test_range','test_family'):
            self.assertFalse(train & {(r['prompt'],r['answer']) for r in d[split]})

if __name__=='__main__':unittest.main()
