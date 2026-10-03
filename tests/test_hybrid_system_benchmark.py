import sys,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
import hybrid_system_v015 as h

class HybridSystemBenchmarkTests(unittest.TestCase):
    def test_route_metadata_is_parsed(self):
        m=h.parse_meta('[route=calculator neural=0 loops=0 token_score=1]')
        self.assertEqual(m['route'],'calculator')
        self.assertFalse(m['neural_used'])
        self.assertEqual(m['loops'],0)
        self.assertEqual(m['token_score'],1.0)

    def test_neural_route_metadata_is_parsed(self):
        m=h.parse_meta('[route=neural neural=1 loops=2 token_score=0.25]')
        self.assertEqual(m['route'],'neural')
        self.assertTrue(m['neural_used'])
        self.assertEqual(m['loops'],2)

    def test_legacy_metadata_is_rejected(self):
        with self.assertRaises(ValueError):
            h.parse_meta('[neural=0 loops=0 token_score=1]')

if __name__=='__main__':
    unittest.main()
