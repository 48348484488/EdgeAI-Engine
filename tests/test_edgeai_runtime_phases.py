"""Regression tests for observed CPU phase timing; no simulated game FPS."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "edgeai_runtime_phases.py"
spec = importlib.util.spec_from_file_location("edgeai_runtime_phases", SCRIPT)
phase = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phase)


def line(frames=60, pose=8.0, vbo=3.0, draw=10.0, work=30.0):
    return ("10-30 19:01:02 raylib LIOS_PHASE_TIMING frames=%d "
            "pose_cpu_ms=%.3f vbo_submit_ms=%.3f "
            "end_drawing_ms=%.3f frame_work_ms=%.3f\n" %
            (frames, pose, vbo, draw, work))


class PhaseAuditTests(unittest.TestCase):
    def test_weighted_means_and_unattributed_work(self):
        result = phase.summarize(line(60, 8, 3, 10, 30) +
                                 line(30, 2, 1, 8, 20))
        self.assertEqual(result["observed_frames"], 90)
        self.assertEqual(result["mean_phase_ms"]["pose_cpu_ms"], 6.0)
        self.assertAlmostEqual(result["mean_phase_ms"]["frame_work_ms"], 26.6667)
        self.assertEqual(result["largest_observed_cpu_component"],
                         "end_drawing_ms")
        self.assertFalse(result["original_game_parity_proven"])

    def test_missing_log_is_not_invented(self):
        with self.assertRaisesRegex(ValueError, "no observed"):
            phase.summarize("FPS: 60")

    def test_reject_invalid_phase_totals(self):
        with self.assertRaisesRegex(ValueError, "exceed"):
            phase.summarize(line(work=15))

    def test_reject_duplicate_and_missing_metrics(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            phase.summarize(line().replace(
                "frame_work_ms=30.000", "pose_cpu_ms=1 frame_work_ms=30.000"))
        with self.assertRaisesRegex(ValueError, "missing"):
            phase.summarize(line().replace("vbo_submit_ms=3.000 ", ""))

    def test_generic_marker_and_custom_keys(self):
        trace = "GAME_CPU frames=4 physics_ms=1.5 frame_work_ms=5.0\n"
        result = phase.summarize(
            trace, marker="GAME_CPU", keys=("physics_ms", "frame_work_ms"))
        self.assertEqual(result["observed_frames"], 4)
        self.assertEqual(result["mean_phase_ms"]["physics_ms"], 1.5)

    def test_reject_inconsistent_windows(self):
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            phase.summarize(line() + line().replace(
                "frame_work_ms=30.000", "frame_work_ms=30.000 physics_ms=1"))

    def test_compare_reports_change_not_gpu_time(self):
        base = phase.summarize(line(work=30))
        newer = phase.summarize(line(pose=6, work=25))
        report = phase.compare(newer, base)
        self.assertAlmostEqual(
            report["mean_phase_change_pct"]["frame_work_ms"], -16.667)
        self.assertFalse(report["gpu_execution_time_measured"])


if __name__ == "__main__":
    unittest.main()
