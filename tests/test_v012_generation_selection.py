import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))

import instruction_blocks_generation_select_v012 as gs


class GenerationSelectionV012Tests(unittest.TestCase):
    def test_selection_prefers_more_greedy_correct_over_lower_nll(self):
        rows=[
            dict(step=100,greedy_correct=7,greedy_exact=7,validation_nll=.20),
            dict(step=200,greedy_correct=8,greedy_exact=6,validation_nll=.40),
        ]
        self.assertEqual(gs.select_checkpoint(rows)['step'],200)

    def test_selection_tiebreaks_exact_then_nll_then_earlier_step(self):
        rows=[
            dict(step=400,greedy_correct=8,greedy_exact=6,validation_nll=.20),
            dict(step=300,greedy_correct=8,greedy_exact=7,validation_nll=.50),
            dict(step=200,greedy_correct=8,greedy_exact=7,validation_nll=.30),
            dict(step=100,greedy_correct=8,greedy_exact=7,validation_nll=.30),
        ]
        self.assertEqual(gs.select_checkpoint(rows)['step'],100)

    def test_generation_metrics_uses_validation_rows_only_as_given(self):
        rows=[
            dict(task='copy',prompt='p1',answer='a',id='v1'),
            dict(task='copy',prompt='p2',answer='b',id='v2'),
        ]
        outputs={'p1':(b'a',True),'p2':(b'x',False)}
        got=gs.generation_metrics_from_outputs(rows,outputs)
        self.assertEqual(got['count'],2)
        self.assertEqual(got['correct'],1)
        self.assertEqual(got['exact'],1)
        self.assertEqual(got['eos'],1)


if __name__=='__main__':
    unittest.main()
