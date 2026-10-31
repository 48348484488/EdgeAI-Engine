import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgeai_swept_collision_audit import audit, intersects


class SweptCollisionTests(unittest.TestCase):
    def test_tunnel_through_thin_wall(self):
        spec = {"cases": [{"name": "fast_wall_crossing", "start": [3, -2.3],
                           "end": [3, -0.7], "colliders": [
                               {"center": [3, -1.5], "half_extents": [1.5, .38]}],
                           "expected_blocked": True}]}
        result = audit(spec)
        self.assertTrue(result["ok"])
        self.assertEqual(result["endpoint_misses"], 1)

    def test_wall_endcap(self):
        c, h = [3, -1.5], [1.5, .38]
        self.assertTrue(intersects([4.49, -2.3], [4.49, -.7], c, h))
        self.assertFalse(intersects([4.51, -2.3], [4.51, -.7], c, h))

    def test_parallel_and_diagonal(self):
        c, h = [3, -1.5], [1.5, .38]
        self.assertFalse(intersects([3, 0], [3, .2], c, h))
        self.assertTrue(intersects([1, -3], [5, 0], c, h))

    def test_spawn_inside_can_exit(self):
        case = {"cases": [{"start": [3, -1.5], "end": [3, 0],
                           "colliders": [{"center": [3, -1.5],
                                          "half_extents": [1.5, .38]}],
                           "expected_blocked": False}]}
        self.assertTrue(audit(case)["ok"])

    def test_expected_mismatch_fails(self):
        case = {"cases": [{"start": [0, 0], "end": [2, 0],
                           "colliders": [{"center": [1, 0],
                                          "half_extents": [.1, .1]}],
                           "expected_blocked": False}]}
        self.assertFalse(audit(case)["ok"])

    def test_reject_invalid_numbers(self):
        for bad in (float("nan"), float("inf"), True, "1"):
            with self.assertRaises(ValueError):
                intersects([bad, 0], [1, 1], [0, 0], [.5, .5])
        with self.assertRaises(ValueError):
            intersects([0, 0], [1, 1], [0, 0], [-1, .5])


if __name__ == "__main__":
    unittest.main()
