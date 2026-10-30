"""Regression tests for generic UI screenshot-to-touch evidence correlation."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "edgeai_ui_interaction_audit.py"
spec = importlib.util.spec_from_file_location("edgeai_ui_interaction_audit", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sample():
    return {"source_resolution": [1920, 1080], "target_resolution": [1080, 640],
            "controls": [
                {"name": "craft", "source_center": [61, 1025],
                 "observed_center": [34, 480], "source_bounds": [11, 975, 111, 1075]},
                {"name": "inventory", "source_center": [513, 977],
                 "observed_center": [288.5625, 453]},
                {"name": "settings", "source_center": [1855, 355],
                 "observed_center": [1043.4375, 103]},
            ],
            "touch_trials": [
                {"control": "craft", "screen_point": [34, 480], "action_observed": False},
                {"control": "craft", "screen_point": [34, 593], "action_observed": True},
            ]}


class InteractionAuditTests(unittest.TestCase):
    def test_historical_misaligned_touch_evidence(self):
        result = module.audit(sample())
        self.assertTrue(result["alignment"]["alignment_passed"])
        self.assertEqual(result["geometry_runtime_disagreements"], 2)
        self.assertEqual([r["verdict"] for r in result["touch_trials"]],
                         ["inside_but_no_activation", "outside_but_activated"])
        self.assertFalse(result["original_game_parity_proven"])

    def test_corrected_touch_is_confirmed_only_when_observed(self):
        data = sample()
        data["touch_trials"] = [{"control": "craft", "screen_point": [34, 480],
                                 "action_observed": True}]
        result = module.audit(data)
        self.assertEqual(result["geometry_runtime_disagreements"], 0)
        self.assertEqual(result["observed_activation_count"], 1)
        self.assertEqual(result["touch_trials"][0]["verdict"], "observed_inside_activation")

    def test_real_screenshot_and_action_event_both_required(self):
        data = sample()
        data["touch_trials"] = [{"control": "craft", "screen_point": [34, 480],
                                 "action_observed": True,
                                 "visual_transition_observed": True}]
        result = module.audit(data)
        self.assertEqual(result["action_and_visual_transition_confirmed_count"], 1)
        self.assertEqual(result["visual_runtime_disagreements"], 0)
        self.assertTrue(result["touch_trials"][0]["action_and_visual_transition_confirmed"])
        self.assertEqual(result["touch_trials"][0]["visual_verdict"],
                         "action_and_visual_transition_observed")
        self.assertFalse(result["original_game_parity_proven"])

    def test_log_only_and_visual_only_do_not_confirm_action_transition(self):
        data = sample()
        data["touch_trials"] = [
            {"control": "craft", "screen_point": [34, 480],
             "action_observed": True, "visual_transition_observed": False},
            {"control": "craft", "screen_point": [34, 480],
             "action_observed": False, "visual_transition_observed": True},
        ]
        result = module.audit(data)
        self.assertEqual(result["action_and_visual_transition_confirmed_count"], 0)
        self.assertEqual(result["visual_runtime_disagreements"], 2)
        self.assertEqual([x["visual_verdict"] for x in result["touch_trials"]],
                         ["action_logged_without_visual_transition",
                          "visual_change_without_action_log"])

    def test_real_android_craft_transition_evidence(self):
        import json
        evidence = (Path(__file__).resolve().parents[1] / "docs" /
                    "last_android_craft_transition_verified_2026-10-30.json")
        data = json.loads(evidence.read_text(encoding="utf-8"))
        result = module.audit(data)
        self.assertTrue(result["alignment"]["alignment_passed"])
        self.assertEqual(result["geometry_runtime_disagreements"], 0)
        self.assertEqual(result["action_and_visual_transition_confirmed_count"], 1)
        self.assertEqual(result["visual_runtime_disagreements"], 0)
        self.assertFalse(result["original_game_parity_proven"])

    def test_visual_evidence_requires_explicit_boolean(self):
        data = sample()
        data["touch_trials"][0]["visual_transition_observed"] = "yes"
        with self.assertRaisesRegex(ValueError, "visual_transition_observed"):
            module.audit(data)
        data["touch_trials"][0]["visual_transition_observed"] = None
        with self.assertRaisesRegex(ValueError, "visual_transition_observed"):
            module.audit(data)

    def test_invalid_and_missing_touch_evidence_rejected(self):
        data = sample()
        data["touch_trials"][0]["action_observed"] = "yes"
        with self.assertRaisesRegex(ValueError, "explicit boolean"):
            module.audit(data)
        data = sample()
        data["touch_trials"] = []
        with self.assertRaisesRegex(ValueError, "at least one"):
            module.audit(data)

    def test_outlier_prevents_unfounded_runtime_verdict(self):
        data = sample()
        data["controls"][-1]["observed_center"] = [1043, 170]
        result = module.audit(data)
        self.assertFalse(result["alignment"]["alignment_passed"])
        self.assertEqual(result["touch_trials"][0]["verdict"], "geometry_unreliable")

    def test_invalid_rectangles_and_unknown_controls(self):
        data = sample()
        data["controls"][0]["source_bounds"] = [111, 975, 11, 1075]
        with self.assertRaisesRegex(ValueError, "positive area"):
            module.audit(data)
        data = sample()
        data["touch_trials"][0]["control"] = "not_a_control"
        with self.assertRaisesRegex(ValueError, "unknown control"):
            module.audit(data)


if __name__ == "__main__":
    unittest.main()
