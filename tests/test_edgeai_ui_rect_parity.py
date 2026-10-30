import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from edgeai_ui_rect_parity import analyze


def fixture():
    return {'schema':'edgeai.ui-rect-parity.v1',
            'reference_provenance':'source Unity LITE 7.3 RectTransform',
            'reference_canvas':[1920,1080], 'candidate_canvas':[1920,1080],
            'controls':[{'name':'back','reference':[1654,0,316,86],
                         'render':[1654,0,316,86], 'hit':[1654,0,316,86]}]}


class RectParityTests(unittest.TestCase):
    def test_exact_source_geometry(self):
        report=analyze(fixture())
        self.assertEqual(report['issues'],0)
        self.assertFalse(report['visual_or_behavioral_parity_proven'])

    def test_detects_last_original_back_hitbox_gap(self):
        data=fixture();data['controls'][0]['hit']=[1654,0,266,86]
        report=analyze(data)
        self.assertEqual(report['issues'],1)
        self.assertAlmostEqual(report['controls'][0]['render_hit_dead_fraction'],50/316,places=5)

    def test_detects_wrong_subtab_spacing(self):
        data=fixture();data['controls'][0]['reference']=[255.3+145*3,151.1,120,35]
        data['controls'][0]['render']=[255.3+124*3,151.1,120,35]
        data['controls'][0]['hit']=data['controls'][0]['render']
        self.assertIn('source_render_geometry_mismatch',analyze(data)['controls'][0]['issues'])

    def test_resolution_scaling(self):
        data=fixture();data['candidate_canvas']=[960,540]
        data['controls'][0]['render']=[827,0,158,43]
        data['controls'][0]['hit']=[827,0,158,43]
        self.assertEqual(analyze(data)['issues'],0)

    def test_rejects_nonfinite_geometry_and_duplicates(self):
        data=fixture();data['controls'][0]['hit']=[0,0,float('nan'),10]
        with self.assertRaisesRegex(ValueError,'finite'):
            analyze(data)
        data=fixture();data['controls'].append(data['controls'][0].copy())
        with self.assertRaisesRegex(ValueError,'duplicate'):
            analyze(data)

    def test_requires_provenance(self):
        data=fixture();data.pop('reference_provenance')
        with self.assertRaisesRegex(ValueError,'provenance'):
            analyze(data)


if __name__=='__main__':
    unittest.main()
