import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgeai_movement_trace_audit import audit_trace


def fixture():
    positions = [0., .2, .4, .8, .8]
    targets = [.2, .4, .8, 1.05, 1.05]
    return {"records": [
        {"frame": i*10+10, "x": x, "z": 0., "target_x": target,
         "target_z": 0., "blocked": int(i>=3), "terrain": 0}
        for i, (x, target) in enumerate(zip(positions, targets))],
        "colliders": [{"center": [1., 0.], "half_extents": [.1, .5]}],
        "min_travel": .15}


class MovementTraceAuditTests(unittest.TestCase):
    def retreat_fixture(self):
        positions = [.8, .6, .4, .2, 0.]
        targets = [.6, .4, .2, 0., -.2]
        return {"mode": "retreat", "records": [
            {"frame": i*10+100, "x": x, "z": 0., "target_x": target,
             "target_z": 0., "blocked": 0, "terrain": 0}
            for i, (x, target) in enumerate(zip(positions, targets))],
            "colliders": [{"center": [1., 0.], "half_extents": [.1, 1.]}]}

    def test_retreat_from_wall(self):
        result = audit_trace(self.retreat_fixture())
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["mode"], "retreat")
        self.assertGreater(result["clearance_gain_m"], .5)

    def test_retreat_requires_clearance_gain(self):
        spec = self.retreat_fixture()
        for i, row in enumerate(spec["records"]):
            row.update(x=.8, z=i*.2, target_x=.8, target_z=(i+1)*.2)
        result = audit_trace(spec)
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"]["retreat_clearance"])

    def test_retreat_rejects_false_collision_flag(self):
        spec = self.retreat_fixture()
        spec["records"][2]["blocked"] = 1
        self.assertFalse(audit_trace(spec)["ok"])

    def test_retreat_rejects_invalid_mode(self):
        spec = self.retreat_fixture()
        spec["mode"] = "teleport"
        with self.assertRaises(ValueError):
            audit_trace(spec)

    def test_realistic_contact(self):
        r = audit_trace(fixture())
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["oracle_matches"], 5)
        self.assertFalse(r["original_game_parity_verified"])

    def test_oracle_mismatch(self):
        s = fixture()
        s["records"][1]["blocked"] = 1
        self.assertFalse(audit_trace(s)["ok"])

    def test_no_contact(self):
        s = fixture()
        for r in s["records"]:
            r["blocked"] = 0
        self.assertFalse(audit_trace(s)["ok"])

    def test_unstable_contact(self):
        s = fixture()
        s["records"][-1]["x"] = .6
        self.assertFalse(audit_trace(s)["ok"])

    def test_bad_frame_order(self):
        s = fixture()
        s["records"][2]["frame"] = s["records"][1]["frame"]
        with self.assertRaises(ValueError):
            audit_trace(s)

    def test_nonfinite_or_boolean_coordinate(self):
        for invalid in (float("nan"), float("inf"), True, "0"):
            s = fixture()
            s["records"][0]["x"] = invalid
            with self.assertRaises(ValueError):
                audit_trace(s)

    def test_invalid_geometry(self):
        s = fixture()
        s["colliders"][0]["half_extents"] = [0, .5]
        with self.assertRaises(ValueError):
            audit_trace(s)

    def test_boundary_tolerance(self):
        s = fixture()
        s["records"][3]["target_x"] = .90001
        s["records"][3]["blocked"] = 0
        result = audit_trace(s)
        self.assertGreaterEqual(result["boundary_ambiguous"], 1)


if __name__ == "__main__":
    unittest.main()
