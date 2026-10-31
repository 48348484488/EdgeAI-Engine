"""Regression tests for generic visibility/work telemetry."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgeai_visibility_phase_audit import audit


def window(visible, calls, cost, frames=60):
    return ("LIOS_PHASE_TIMING frames=%d pose_cpu_ms=%s "
            "vbo_submit_ms=0.5 end_drawing_ms=12 "
            "frame_work_ms=30 visible_frames=%d pose_calls=%d\n" %
            (frames, cost, visible, calls))


class VisibilityPhaseAuditTests(unittest.TestCase):
    def test_full_visibility_and_hidden(self):
        result = audit(window(60, 60, "14.0") + window(0, 0, "0.0"))
        self.assertEqual(result["observed_frames"], 120)
        self.assertEqual(result["work_calls"], 60)
        self.assertEqual(result["groups"]["visible"]["mean_cpu_work_ms"], 14.0)
        self.assertEqual(result["groups"]["hidden"]["mean_cpu_work_ms"], 0.0)
        self.assertFalse(result["original_game_parity_proven"])

    def test_mixed_window_is_not_misattributed(self):
        result = audit(window(22, 22, "5.2"))
        self.assertEqual(result["groups"]["mixed"]["frames"], 60)
        self.assertIsNone(result["groups"]["visible"]["mean_cpu_work_ms"])

    def test_detect_hidden_work(self):
        with self.assertRaisesRegex(ValueError, "invisible"):
            audit(window(0, 0, "1.2"))

    def test_reject_work_calls_exceed_visibility(self):
        with self.assertRaisesRegex(ValueError, "invariant"):
            audit(window(5, 6, "0.3"))

    def test_reject_missing_metrics(self):
        with self.assertRaisesRegex(ValueError, "missing"):
            audit("LIOS_PHASE_TIMING frames=60 pose_cpu_ms=0.0\n")

    def test_reject_duplicate_metric(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit(window(60, 60, "14.0").replace("pose_calls=60",
                                                  "pose_calls=60 pose_calls=60"))

    def test_reject_invalid_tolerance(self):
        with self.assertRaisesRegex(ValueError, "tolerance"):
            audit(window(0, 0, "0.0"), hidden_tolerance_ms=float("nan"))

    def test_accept_other_engine_keys(self):
        log = "GAME_PROFILE frames=10 mesh_ms=0 visible=0 calls=0\n"
        result = audit(log, "GAME_PROFILE", "visible", "calls", "mesh_ms")
        self.assertEqual(result["groups"]["hidden"]["frames"], 10)


if __name__ == "__main__":
    unittest.main()
