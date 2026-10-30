"""Deterministic source-tile adjacency and malformed-catalog regressions."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "edgeai_tile_catalog.py"
spec = importlib.util.spec_from_file_location("edgeai_tile_catalog", SCRIPT)
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class CatalogTests(unittest.TestCase):
    def parse(self, data):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "tiles.txt"
            p.write_text(data, encoding="utf8")
            return module.parse_catalog(p)

    def test_four_neighbors_and_oversized_mesh_rejected(self):
        rows = [
            "center.obj center.png -200 200 -200 200 0 30",
            "north.obj n.png -200 200 200 600 0 50",
            "south.obj s.png -200 200 -600 -200 0 50",
            "east.obj e.png 200 600 -200 200 0 50",
            "west.obj w.png -600 -200 -200 200 0 50",
            "world.obj w.png -20000 20000 -20000 20000 -200 500",
        ]
        result = module.adjacent_tiles(self.parse("\n".join(rows)), "center.obj")
        self.assertEqual({k: v.mesh for k, v in result.items()},
                         {"north": "north.obj", "south": "south.obj",
                          "east": "east.obj", "west": "west.obj"})

    def test_gaps_and_short_edge_overlap_are_rejected(self):
        rows = ["c.obj c.png -200 200 -200 200 0 30",
                "gap.obj g.png 202 602 -200 200 0 30",
                "sliver.obj s.png -200 200 200 600 0 30",
                "partial.obj p.png 200 600 150 550 0 30"]
        result = module.adjacent_tiles(self.parse("\n".join(rows)), "c.obj")
        self.assertEqual(set(result), {"north"})

    def test_rejects_bad_manifest_entries(self):
        cases = [
            "a.obj a.png 0 nan 0 1 0 1",
            "a.obj a.png 2 1 0 1 0 1",
            "../a.obj a.png 0 1 0 1 0 1",
            "a.obj a.png 0 1 0 1 0 1\na.obj b.png 0 1 0 1 0 1",
            "a.obj a.png 0 1 0 1 0",
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.parse(case)

    def test_missing_anchor_and_invalid_tolerances(self):
        rows = self.parse("c.obj c.png 0 1 0 1 0 1")
        with self.assertRaises(ValueError):
            module.adjacent_tiles(rows, "missing.obj")
        with self.assertRaises(ValueError):
            module.adjacent_tiles(rows, "c.obj", gap_tolerance=-1)


if __name__ == "__main__":
    unittest.main()
