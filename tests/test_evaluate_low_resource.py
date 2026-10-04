import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evaluate", ROOT / "tools" / "evaluate_low_resource.py")
evaluate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate)


class EvaluatorTests(unittest.TestCase):
    def test_duplicate_ids_rejected(self):
        rows = [{"id": "x"}, {"id": "x"}]
        with self.assertRaises(ValueError):
            evaluate.validate_corpus(rows)

    def test_route_and_exact_answer_are_scored(self):
        item = {"id": "calc", "category": "tool", "expected_route": "calculator", "expected_text": "4"}
        self.assertTrue(evaluate.score(item, {"route": "calculator", "text": "4", "neural_used": False})[0])
        self.assertFalse(evaluate.score(item, {"route": "neural", "text": "4", "neural_used": True})[0])
        self.assertFalse(evaluate.score(item, {"route": "calculator", "text": "5", "neural_used": False})[0])

    def test_neural_empty_is_malformed(self):
        item = {"id": "n", "category": "neural", "expected_route": "neural", "rubric": "nonempty"}
        passed, malformed, _ = evaluate.score(item, {"route": "neural", "text": "", "neural_used": True})
        self.assertFalse(passed)
        self.assertTrue(malformed)

    def test_neural_human_review_defaults_to_fail(self):
        item = {"id": "n", "category": "neural", "expected_route": "neural", "rubric": "human_review"}
        passed, malformed, _ = evaluate.score(item, {"route": "neural", "text": "words", "neural_used": True})
        self.assertFalse(passed)
        self.assertFalse(malformed)

    def test_summary_keeps_tool_and_neural_separate(self):
        records = [
            {"category": "tool", "passed": True, "malformed": False, "latency_ms": 1},
            {"category": "neural", "passed": False, "malformed": True, "latency_ms": 2},
        ]
        summary = evaluate.summarize(records)
        self.assertEqual(summary["tool_accuracy"], 1.0)
        self.assertEqual(summary["neural_rubric_pass_rate"], 0.0)
        self.assertNotIn("accuracy", summary)

    def test_human_approval_is_bound_to_response_hash(self):
        item = {"id": "n", "category": "neural", "expected_route": "neural", "rubric": "human_review",
                "manual_pass": True, "expected_response_sha256": "wrong"}
        passed, _, _ = evaluate.score(item, {"route": "neural", "text": "changed", "neural_used": True})
        self.assertFalse(passed)


if __name__ == "__main__":
    unittest.main()
