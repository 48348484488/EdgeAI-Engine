"""Regression tests for generic transition-frame input ownership."""
import importlib.util
from pathlib import Path
import unittest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "edgeai_transition_input_audit.py"
SPEC = importlib.util.spec_from_file_location("edgeai_transition_input_audit", TOOL)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TransitionInputAuditTests(unittest.TestCase):
    def test_transition_consumes_opening_touch(self):
        log = (
            "raylib: LIOS_INPUT_TRANSITION frame=42 from=game to=build\n"
            "raylib: LIOS_INPUT_DISPATCH frame=43 scope=build\n"
        )
        result = MODULE.audit(log)
        self.assertTrue(result["validated"])
        self.assertEqual(result["transition_count"], 1)
        self.assertEqual(result["violation_count"], 0)

    def test_same_frame_dispatch_into_new_scope_is_failure(self):
        log = (
            "LIOS_INPUT_TRANSITION frame=42 from=game to=build\n"
            "LIOS_INPUT_DISPATCH frame=42 scope=build\n"
        )
        result = MODULE.audit(log)
        self.assertEqual(result["violation_count"], 1)
        self.assertEqual(
            result["violations"][0]["reason"],
            "new_scope_received_transition_frame_touch"
        )

    def test_other_scope_does_not_create_false_positive(self):
        result = MODULE.audit(
            "INPUT_TRANSITION frame=9 from=game to=panel_2\n"
            "INPUT_DISPATCH frame=9 scope=game\n"
        )
        self.assertTrue(result["validated"])

    def test_malformed_markers_are_not_silently_ignored(self):
        result = MODULE.audit("INPUT_TRANSITION frame=broken from=game to=build")
        self.assertEqual(result["violations"][0]["reason"], "invalid_transition")
        self.assertFalse(result["validated"])

    def test_empty_trace_is_not_reported_as_validated(self):
        result = MODULE.audit("no touch events")
        self.assertFalse(result["validated"])
        self.assertEqual(result["violation_count"], 0)


if __name__ == "__main__":
    unittest.main()
