import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import instruction_data_v013 as v13

class CurriculumV013Tests(unittest.TestCase):
    def test_sealed_v012_tests_never_enter_training(self):
        d=v13.build_v013();train={(r['prompt'],r['answer']) for r in d['train']}
        for split in ('test_id','test_template','test_range','test_family'):
            self.assertFalse(train & {(r['prompt'],r['answer']) for r in d[split]})
    def test_reverse_remains_fully_held_out(self):
        d=v13.build_v013()
        self.assertNotIn('reverse',{r['task'] for r in d['train']})
        self.assertEqual({r['task'] for r in d['test_family']},{'reverse'})
    def test_expansion_stops_before_extrapolation_bounds(self):
        d=v13.build_v013(); prompts='\n'.join(r['prompt'] for r in d['train'])
        self.assertIn('Add: 29 + 29',prompts);self.assertNotIn('Add: 30 + 30',prompts)
        self.assertIn('Expression for x + 39:',prompts);self.assertNotIn('Expression for x + 40:',prompts)

if __name__=='__main__':unittest.main()
