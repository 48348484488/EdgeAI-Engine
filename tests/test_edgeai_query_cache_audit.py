"""Tests for architecture-neutral mesh query cache runtime auditor."""
import importlib.util
from pathlib import Path
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "edgeai_query_cache_audit.py"
SPEC = importlib.util.spec_from_file_location("edgeai_query_cache_audit", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class QueryCacheAuditTests(unittest.TestCase):
    def test_valid_counts_and_ratio(self):
        result = MODULE.audit("INFO LIOS_TERRAIN_SAMPLE_CACHE calls=600 hits=420 misses=180")
        self.assertTrue(result["passed"])
        self.assertEqual(result["windows"], 1)
        self.assertAlmostEqual(result["hit_ratio"], 0.7)
        self.assertFalse(result["fps_improvement_proven"])

    def test_inconsistent_counters(self):
        result = MODULE.audit("SAMPLE_CACHE calls=600 hits=600 misses=1")
        self.assertFalse(result["passed"])
        self.assertEqual(result["violations"][0]["reason"], "counter_mismatch")

    def test_no_observations_is_not_a_pass(self):
        self.assertFalse(MODULE.audit("unrelated engine log")["passed"])

    def test_malformed_line(self):
        result = MODULE.audit("SAMPLE_CACHE hits=12 calls=12 misses=0")
        self.assertFalse(result["passed"])
        self.assertEqual(result["violations"][0]["reason"], "invalid_counters")

    def test_multiple_windows_custom_marker(self):
        result = MODULE.audit("Q calls=10 hits=9 misses=1\nQ calls=10 hits=1 misses=9",
                              marker="Q", minimum_windows=2)
        self.assertTrue(result["passed"])
        self.assertAlmostEqual(result["hit_ratio"], 0.5)


if __name__ == "__main__":
    unittest.main()
