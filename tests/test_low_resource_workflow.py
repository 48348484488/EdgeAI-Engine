import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WorkflowContract(unittest.TestCase):
    def test_frozen_corpus_keeps_canonical_line_endings(self):
        path = ROOT / ".gitattributes"
        self.assertTrue(path.exists(), ".gitattributes must define the corpus checkout format")
        text = path.read_text(encoding="utf-8")
        self.assertIn("data/low_resource_v016/*.jsonl text eol=lf", text)

    def test_low_resource_workflow_has_required_gates(self):
        text = (ROOT / ".github/workflows/low-resource-ci.yml").read_text(encoding="utf-8")
        for token in ("contents: read", "EDGEAI_LOW_RESOURCE=ON", "test_low_resource_composition.py",
                      "test_measure_low_resource", "test_evaluate_low_resource", "upload-artifact@v4",
                      "--workload data/low_resource_v016/workload.txt", "--baseline results/v016_low_resource/baseline.json"):
            self.assertIn(token, text)
        self.assertNotIn("write-all", text)


if __name__ == "__main__":
    unittest.main()
