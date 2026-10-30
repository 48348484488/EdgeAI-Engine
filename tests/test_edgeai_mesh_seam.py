"""Seam differential tests using independently defined triangles."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location("edgeai_mesh_seam", TOOLS / "edgeai_mesh_seam.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
from edgeai_obj_surface import Surface


class SeamTests(unittest.TestCase):
    def load(self, vertices, height=0):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tile.obj"
            path.write_text(vertices, encoding="utf8")
            return Surface.from_obj(path, axis="y-up")

    def test_continuous_ground_passes(self):
        left = self.load("v 0 2 0\nv 1 2 0\nv 0 2 1\nv 1 2 1\nf 1 2 3\nf 2 4 3\n")
        right = self.load("v 1 2 0\nv 2 2 0\nv 1 2 1\nv 2 2 1\nf 1 2 3\nf 2 4 3\n")
        result = mod.audit_seam(left, right, [(0.9, 0.5, 1.1, 0.5)])
        self.assertTrue(result["pass"])
        self.assertEqual(result["probes"][0]["delta"], 0.0)

    def test_large_step_and_missing_surface_fail(self):
        left = self.load("v 0 0 0\nv 1 0 0\nv 0 0 1\nf 1 2 3\n")
        right = self.load("v 1 2 0\nv 2 2 0\nv 1 2 1\nf 1 2 3\n")
        result = mod.audit_seam(left, right, [(0.1, 0.1, 1.1, 0.1),
                                              (3, 3, 1.1, 0.1)])
        self.assertFalse(result["pass"])
        self.assertEqual(result["covered_count"], 1)
        self.assertEqual(result["probes"][0]["delta"], 2.0)

    def test_nonfinite_probe_and_negative_threshold_rejected(self):
        tile = self.load("v 0 0 0\nv 1 0 0\nv 0 0 1\nf 1 2 3\n")
        with self.assertRaises(ValueError):
            mod.audit_seam(tile, tile, [(float("nan"), 0, 0, 0)])
        with self.assertRaises(ValueError):
            mod.audit_seam(tile, tile, [(0, 0, 0, 0)], -1)
        with self.assertRaises(ValueError):
            mod.audit_seam(tile, tile, [])


if __name__ == "__main__":
    unittest.main()
