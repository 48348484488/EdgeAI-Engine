import unittest
from tools.edgeai_event_sequence_audit import audit

RULES = {
    "steps": [
        {"name": "craft", "pattern": "CRAFT_QUEUED"},
        {"name": "ready", "pattern": "BLUEPRINT_READY"},
        {"name": "enter", "pattern": "MODE_ENTER"},
        {"name": "category", "pattern": "CATEGORY_2"},
        {"name": "child", "pattern": "CHILD_0"},
        {"name": "place", "pattern": "PLACE_1"},
        {"name": "exit", "pattern": "MODE_EXIT"},
    ],
    "forbidden_between": [
        {"start": "enter", "end": "exit", "pattern": "ATTACK_TRIGGERED"}
    ],
    "forbidden_same_frame": [
        {"name": "opening_tap", "start_pattern": r"TRANSITION frame=(?P<frame>\d+)",
         "forbidden_pattern": r"DISPATCH frame=(?P<frame>\d+)"}
    ],
}

VALID = "\n".join([
    "CRAFT_QUEUED", "BLUEPRINT_READY", "TRANSITION frame=42",
    "MODE_ENTER", "CATEGORY_2", "DISPATCH frame=43",
    "CHILD_0", "PLACE_1", "MODE_EXIT"
])


class EventSequenceAuditTests(unittest.TestCase):
    def test_valid_order_and_different_frame(self):
        result = audit(VALID, RULES)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["matched_steps"]), 7)

    def test_missing_step(self):
        result = audit(VALID.replace("BLUEPRINT_READY", "NO_BLUEPRINT"), RULES)
        self.assertFalse(result["ok"])
        self.assertIn("missing_or_out_of_order:ready", result["errors"])

    def test_wrong_order(self):
        text = VALID.replace("CATEGORY_2", "CHILD_0", 1).replace(
            "DISPATCH frame=43\nCHILD_0", "DISPATCH frame=43\nCATEGORY_2")
        result = audit(text, RULES)
        self.assertFalse(result["ok"])

    def test_forbidden_action_inside_mode(self):
        result = audit(VALID.replace("PLACE_1", "ATTACK_TRIGGERED\nPLACE_1"), RULES)
        self.assertFalse(result["ok"])
        self.assertTrue(any(x.startswith("forbidden_between:") for x in result["errors"]))

    def test_same_frame_touch_leak(self):
        result = audit(VALID.replace("DISPATCH frame=43", "DISPATCH frame=42"), RULES)
        self.assertFalse(result["ok"])
        self.assertTrue(any(x.startswith("same_frame_leak:") for x in result["errors"]))

    def test_missing_frame_anchor(self):
        result = audit(VALID.replace("TRANSITION frame=42", "NO_TRANSITION"), RULES)
        self.assertFalse(result["ok"])
        self.assertTrue(any(x.startswith("missing_frame_anchor:") for x in result["errors"]))

    def test_reject_duplicate_steps(self):
        with self.assertRaises(ValueError):
            audit(VALID, {"steps": [{"name": "a", "pattern": "a"},
                                    {"name": "a", "pattern": "b"}]})

    def test_reject_unknown_boundary(self):
        with self.assertRaises(ValueError):
            audit(VALID, {"steps": [{"name": "a", "pattern": "CRAFT"}],
                          "forbidden_between": [
                              {"start": "a", "end": "missing", "pattern": "X"}]})


    def test_numeric_comparison_between_steps(self):
        rules = {"steps": [
            {"name": "foundation", "pattern": r"PLACE count=(?P<count>\\d+)"},
            {"name": "wall", "pattern": r"WALL count=(?P<count>\\d+)"},
        ], "numeric_comparisons": [{
            "left": {"step": "wall", "group": "count"}, "op": "gt",
            "right": {"step": "foundation", "group": "count"}
        }]}
        self.assertTrue(audit("PLACE count=1\\nWALL count=2", rules)["ok"])
        result = audit("PLACE count=1\\nWALL count=1", rules)
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"][0].startswith("numeric_comparison_failed:"))

    def test_numeric_comparison_within_rotation_event(self):
        rules = {"steps": [{"name": "rotate",
            "pattern": r"ROTATE before=(?P<before>\\d+) after=(?P<after>\\d+)"}],
            "numeric_comparisons": [{
                "left": {"step": "rotate", "group": "after"}, "op": "ne",
                "right": {"step": "rotate", "group": "before"}}
            ]}
        self.assertTrue(audit("ROTATE before=0 after=1", rules)["ok"])
        self.assertFalse(audit("ROTATE before=0 after=0", rules)["ok"])

    def test_numeric_comparison_rejects_invalid_specification(self):
        rules = {"steps": [{"name": "x", "pattern": r"X (?P<n>\\d+)"}],
                 "numeric_comparisons": [{
                     "left": {"step": "x", "group": "n"}, "op": "bogus",
                     "right": {"step": "x", "group": "n"}
                 }]}
        with self.assertRaises(ValueError):
            audit("X 2", rules)


if __name__ == "__main__":
    unittest.main()
