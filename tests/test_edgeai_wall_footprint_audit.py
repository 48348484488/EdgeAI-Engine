import unittest
from tools.edgeai_wall_footprint_audit import audit

SPEC = {
    "visual_half_length": 1.5,
    "visual_half_thickness": 0.11,
    "collision_half_length": 1.5,
    "collision_half_thickness": 0.38,
    "edge_offset": 1.5,
}


class WallFootprintAuditTests(unittest.TestCase):
    def test_full_coverage_four_rotations(self):
        result = audit(SPEC)
        self.assertTrue(result["ok"])
        self.assertEqual([r["tangent_axis"] for r in result["rotations"]],
                         ["x", "z", "x", "z"])
        self.assertEqual([r["center_xz"] for r in result["rotations"]],
                         [[0, -1.5], [1.5, 0], [0, 1.5], [-1.5, 0]])
        self.assertAlmostEqual(result["collision_overhang_normal"], 0.27)

    def test_detects_endpoint_gap(self):
        result = audit(dict(SPEC, collision_half_length=1.42))
        self.assertFalse(result["ok"])
        self.assertAlmostEqual(result["endpoint_gap_per_side"], 0.08)
        self.assertIn("visual_endpoint_outside_collider", result["errors"])

    def test_detects_thickness_gap(self):
        result = audit(dict(SPEC, collision_half_thickness=0.05))
        self.assertFalse(result["ok"])
        self.assertAlmostEqual(result["thickness_gap_per_side"], 0.06)

    def test_rejects_bad_dimensions(self):
        for bad in (float("nan"), float("inf"), -1, 0, "1.5", True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                audit(dict(SPEC, edge_offset=bad))

    def test_tolerance(self):
        self.assertTrue(audit(dict(SPEC, collision_half_length=1.4999999))["ok"])
        self.assertFalse(audit(dict(SPEC, collision_half_length=1.499))["ok"])


if __name__ == "__main__":
    unittest.main()
