"""Deterministic tests for observed frame timing log analysis."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "edgeai_frame_pacing.py"
spec = importlib.util.spec_from_file_location("edgeai_frame_pacing", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def log(mean=20.0, p95=30.0, maximum=40.0, slow=3, frames=60):
    return ("2026-10-30 raylib: LIOS_FRAME_TIMING frames=%d mean_ms=%.3f "
            "p95_ms=%.3f max_ms=%.3f slow_33ms=%d mean_fps=%.2f\n"
            % (frames, mean, p95, maximum, slow, 1000.0 / mean))


class FramePacingTests(unittest.TestCase):
    def test_observed_windows_are_weighted(self):
        result = module.summarize(log(20, 30, 40, 3) + log(40, 50, 60, 45))
        self.assertEqual(result["observed_frames"], 120)
        self.assertEqual(result["mean_ms"], 30)
        self.assertEqual(result["mean_fps"], 33.333)
        self.assertEqual(result["slow_33ms"], 48)
        self.assertFalse(result["original_game_parity_proven"])

    def test_custom_engine_marker_is_supported(self):
        trace = log().replace("LIOS_FRAME_TIMING", "ENGINE_FRAME_TIMING")
        with self.assertRaisesRegex(ValueError, "no observed"):
            module.summarize(trace)
        result = module.summarize(trace, marker="ENGINE_FRAME_TIMING")
        self.assertEqual(result["observed_frames"], 60)

    def test_missing_evidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no observed"):
            module.summarize("FPS: 60")

    def test_invalid_or_inconsistent_measurements_rejected(self):
        for case in (log(20, 45, 40), log(20, 30, 40, 61),
                     log(20, 30, 40).replace("mean_fps=50.00", "mean_fps=200.00")):
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    module.summarize(case)

    def test_rare_long_frame_can_make_mean_exceed_p95(self):
        # A single 1-second stall can raise the mean above the 95th
        # percentile; rejecting such logs would hide the worst FPS bugs.
        result = module.summarize(log(26.5, 10, 1000, 1))
        self.assertEqual(result["mean_ms"], 26.5)
        self.assertEqual(result["worst_window_p95_ms"], 10)

    def test_regression_uses_duration_not_fps_difference(self):
        baseline = module.summarize(log(20, 30, 40))
        slower = module.summarize(log(22, 32, 44))
        faster = module.summarize(log(18, 28, 38))
        self.assertTrue(module.compare(slower, baseline, 5)["regression_detected"])
        self.assertFalse(module.compare(faster, baseline, 5)["regression_detected"])

    def test_reject_invalid_threshold(self):
        with self.assertRaisesRegex(ValueError, "threshold"):
            module.compare(module.summarize(log()), module.summarize(log()), -1)


if __name__ == "__main__":
    unittest.main()
