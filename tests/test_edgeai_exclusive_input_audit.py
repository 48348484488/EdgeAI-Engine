"""Regression tests for source-agnostic exclusive UI mode input ownership."""
import importlib.util
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "edgeai_exclusive_input_audit.py"
spec = importlib.util.spec_from_file_location("edgeai_exclusive_input_audit", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

RULES = {
    "enter": "BUILD enabled=1",
    "exit": "BUILD enabled=0",
    "capture": "BUILD_WIDGET_CAPTURE",
    "forbidden": ["JUMP_TRIGGERED", "ATTACK_TRIGGERED", "AIM_TOGGLED"],
}


class ExclusiveInputAuditTests(unittest.TestCase):
    def test_real_mode_capture_and_exit(self):
        log = "BUILD enabled=1\nBUILD_WIDGET_CAPTURE finger=3\nBUILD enabled=0"
        report = module.audit(log, RULES)
        self.assertTrue(report["passed"])
        self.assertEqual(report["captured_touches"], 1)
        self.assertFalse(report["original_game_parity_proven"])

    def test_multiple_build_widget_actions_count_as_captures(self):
        rules = {**RULES, "capture": [
            "BUILD_WIDGET_CAPTURE", "BUILD_CATEGORY", "BUILD_CHILD", "BUILD_PLACE"
        ], "minimum_captures": 3}
        log = ("BUILD enabled=1\nBUILD_WIDGET_CAPTURE finger=1\n"
               "BUILD_CATEGORY category=2\nBUILD_CHILD child=0\nBUILD enabled=0")
        report = module.audit(log, rules)
        self.assertTrue(report["passed"])
        self.assertEqual(report["captured_touches"], 3)

    def test_duplicate_capture_markers_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            module.audit("", {**RULES, "capture": [
                "BUILD_WIDGET_CAPTURE", "BUILD_WIDGET_CAPTURE"
            ]})

    def test_jump_leak_is_rejected(self):
        log = "BUILD enabled=1\nBUILD_WIDGET_CAPTURE\nJUMP_TRIGGERED\nBUILD enabled=0"
        report = module.audit(log, RULES)
        self.assertFalse(report["passed"])
        self.assertTrue(any("gameplay_leak" in v[1] for v in report["violations"]))

    def test_attack_after_exit_is_allowed(self):
        log = "BUILD enabled=1\nBUILD_WIDGET_CAPTURE\nBUILD enabled=0\nATTACK_TRIGGERED"
        self.assertTrue(module.audit(log, RULES)["passed"])

    def test_missing_capture_cannot_pass(self):
        report = module.audit("BUILD enabled=1\nBUILD enabled=0", RULES)
        self.assertIn("insufficient_observed_captures", [v[1] for v in report["violations"]])

    def test_unclosed_mode_cannot_pass(self):
        report = module.audit("BUILD enabled=1\nBUILD_WIDGET_CAPTURE", RULES)
        self.assertIn("mode_not_closed", [v[1] for v in report["violations"]])

    def test_capture_outside_mode_rejected(self):
        report = module.audit("BUILD_WIDGET_CAPTURE\nBUILD enabled=1\nBUILD_WIDGET_CAPTURE\nBUILD enabled=0", RULES)
        self.assertIn("capture_outside_mode", [v[1] for v in report["violations"]])

    def test_no_mode_does_not_pass(self):
        report = module.audit("ATTACK_TRIGGERED", RULES)
        self.assertIn("mode_never_observed", [v[1] for v in report["violations"]])

    def test_invalid_rules_rejected(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            module.audit("", {**RULES, "capture": "BUILD enabled=1"})
        with self.assertRaisesRegex(ValueError, "minimum_captures"):
            module.audit("", {**RULES, "minimum_captures": -1})

    def test_duplicate_enter_rejected(self):
        report = module.audit("BUILD enabled=1\nBUILD enabled=1\nBUILD_WIDGET_CAPTURE\nBUILD enabled=0", RULES)
        self.assertIn("duplicate_enter", [v[1] for v in report["violations"]])


if __name__ == "__main__":
    unittest.main()
