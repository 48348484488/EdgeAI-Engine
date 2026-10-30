"""Regression cases for generic multi-offset runtime/source terrain comparisons."""
import importlib.util
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "edgeai_runtime_seam_audit.py"
spec = importlib.util.spec_from_file_location("edgeai_runtime_seam_grid", SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

REF = {"seams": [
    {"direction": "north", "offset": -75, "inner_height": 2.0, "outer_height": 2.1},
    {"direction": "north", "offset": 0, "inner_height": 3.0, "outer_height": 3.2},
    {"direction": "north", "offset": 75, "inner_height": 4.0, "outer_height": 4.1},
]}
LOG = ("LIOS_TERRAIN_SEAM_GRID_PROBE north offset=-75 inner=1 outer=1 height_in=2 height_out=2.1\n"
       "LIOS_TERRAIN_SEAM_GRID_PROBE north offset=0 inner=1 outer=1 height_in=3 height_out=3.2\n"
       "LIOS_TERRAIN_SEAM_GRID_PROBE north offset=75 inner=1 outer=1 height_in=4 height_out=4.1\n")


class GridAuditTests(unittest.TestCase):
    def audit(self, log=LOG, ref=REF):
        return mod.audit_runtime(log, ref, marker="LIOS_TERRAIN_SEAM_GRID_PROBE")

    def test_all_offsets_checked(self):
        result = self.audit()
        self.assertTrue(result["pass"], result["errors"])
        self.assertEqual(len(result["probes"]), 3)
        self.assertEqual({r["offset"] for r in result["probes"]}, {-75, 0, 75})

    def test_missing_or_duplicate_offset_rejected(self):
        self.assertFalse(self.audit(LOG.splitlines()[0] + "\n")["pass"])
        self.assertIn("duplicate runtime direction: north@75",
                      self.audit(LOG + LOG.splitlines()[2] + "\n")["errors"])

    def test_uncovered_nonfinite_and_excessive_step_rejected(self):
        self.assertFalse(self.audit(LOG.replace("offset=-75 inner=1", "offset=-75 inner=0"))["pass"])
        self.assertFalse(self.audit(LOG.replace("height_out=3.2", "height_out=nan"))["pass"])
        self.assertFalse(self.audit(LOG.replace("height_out=3.2", "height_out=9"))["pass"])

    def test_bad_offset_and_unexpected_probe_rejected(self):
        self.assertFalse(self.audit(LOG.replace("offset=75", "offset=inf"))["pass"])
        self.assertFalse(self.audit(LOG.replace("offset=75", "offset=150"))["pass"])
        self.assertFalse(self.audit(LOG + "LIOS_TERRAIN_SEAM_GRID_PROBE east offset=0 inner=1 outer=1 height_in=1 height_out=1\n")["pass"])

    def test_duplicate_reference_offset_and_malformed_event_rejected(self):
        with self.assertRaises(ValueError):
            self.audit(ref={"seams": REF["seams"] + [REF["seams"][0]]})
        self.assertFalse(self.audit(LOG + "LIOS_TERRAIN_SEAM_GRID_PROBE malformed\n")["pass"])


if __name__ == "__main__":
    unittest.main()
