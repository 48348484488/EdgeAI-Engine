import sys,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
import router_arithmetic_v015 as a

class RouterArithmeticBenchmarkTests(unittest.TestCase):
    def test_corpus_is_unique_and_balanced(self):
        rows=a.cases()
        self.assertEqual(len(rows),96)
        self.assertEqual(len({r['prompt'] for r in rows}),96)
        counts={}
        for r in rows:
            counts[r['task']]=counts.get(r['task'],0)+1
        self.assertEqual(counts,{'subtract':32,'multiply':32,'divide':32})

if __name__=='__main__':
    unittest.main()
