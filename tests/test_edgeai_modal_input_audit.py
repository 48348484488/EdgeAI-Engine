"""Regression tests for modal input ownership in observed runtime logs."""
import importlib.util
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "edgeai_modal_input_audit.py"
spec = importlib.util.spec_from_file_location("edgeai_modal_input_audit", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

RULES = {
    "panels": {"inventory": {"open": "INV_OPEN", "close": "INV_CLOSE"},
               "craft": {"open": "CRAFT_OPEN", "close": "CRAFT_CLOSE"}},
    "gameplay": ["ATTACK", "JUMP"],
    "capture": "MODAL_CAPTURE",
}


class ModalInputAuditTests(unittest.TestCase):
    def test_capture_and_gameplay_after_close(self):
        result = module.audit("INV_OPEN\nMODAL_CAPTURE\nINV_CLOSE\nATTACK", RULES)
        self.assertTrue(result["passed"])
        self.assertEqual(result["opens"], 1)
        self.assertFalse(result["original_game_parity_proven"])

    def test_gameplay_during_modal_is_violation(self):
        result = module.audit("CRAFT_OPEN\nMODAL_CAPTURE\nJUMP\nCRAFT_CLOSE", RULES)
        self.assertFalse(result["passed"])
        self.assertIn("gameplay_during_modal", [v[1] for v in result["violations"]])

    def test_missing_capture_rejected(self):
        result = module.audit("INV_OPEN\nINV_CLOSE", RULES)
        self.assertFalse(result["passed"])

    def test_mismatched_close_rejected(self):
        result = module.audit("INV_OPEN\nMODAL_CAPTURE\nCRAFT_CLOSE", RULES)
        self.assertFalse(result["passed"])

    def test_no_events_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "no observed"):
            module.audit("unrelated output", RULES)


if __name__ == "__main__":
    unittest.main()
