"""Independent synthetic tests for runtime/source seam differential audits."""
import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("runtime_seam", TOOLS / "edgeai_runtime_seam_audit.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

REF = {"seams": [{"direction": "north", "inner_height": 2.0, "outer_height": 2.2},
                 {"direction": "south", "inner_height": 1.0, "outer_height": 1.1}]}
LOG = ("I raylib: LIOS_TERRAIN_SEAM_PROBE north inner=1 outer=1 height_in=2.0000 height_out=2.2000\n"
       "I raylib: LIOS_TERRAIN_SEAM_PROBE south inner=1 outer=1 height_in=1.0000 height_out=1.1000\n")


class RuntimeSeamTests(unittest.TestCase):
    def test_matching_source_and_runtime(self):
        result = mod.audit_runtime(LOG, REF)
        self.assertTrue(result["pass"], result["errors"])
        self.assertEqual(len(result["probes"]), 2)

    def test_missing_and_duplicate_fail(self):
        self.assertFalse(mod.audit_runtime(LOG.splitlines()[0], REF)["pass"])
        self.assertIn("duplicate runtime direction: north", mod.audit_runtime(LOG + LOG, REF)["errors"])

    def test_uncovered_and_wrong_height_fail(self):
        self.assertFalse(mod.audit_runtime(LOG.replace("north inner=1", "north inner=0"), REF)["pass"])
        self.assertFalse(mod.audit_runtime(LOG.replace("height_out=2.2000", "height_out=3.0000"), REF)["pass"])

    def test_nonfinite_and_bad_thresholds(self):
        self.assertFalse(mod.audit_runtime(LOG.replace("height_in=2.0000", "height_in=nan"), REF)["pass"])
        with self.assertRaises(ValueError):
            mod.audit_runtime(LOG, REF, tolerance=-1)

    def test_extra_runtime_direction_fails(self):
        self.assertFalse(mod.audit_runtime(
            LOG + "LIOS_TERRAIN_SEAM_PROBE east inner=1 outer=1 height_in=1 height_out=1\n", REF)["pass"])


if __name__ == "__main__":
    unittest.main()
