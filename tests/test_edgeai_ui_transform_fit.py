"""Generic source-UI to screenshot transform regression tests."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "edgeai_ui_transform_fit.py"
spec = importlib.util.spec_from_file_location("edgeai_ui_transform_fit", SCRIPT)
fit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit_module)

REAL_ANDROID_MATCHES = {
    "source_resolution": [1920, 1080],
    "target_resolution": [1080, 640],
    "controls": [
        {"name": "craft", "source_center": [61, 1025], "observed_center": [34, 480]},
        {"name": "inventory", "source_center": [513.02501, 976.625], "observed_center": [289, 454]},
        {"name": "settings", "source_center": [1854.70078, 354.98001], "observed_center": [1043, 103]},
        {"name": "jump", "source_center": [1834.49316, 789.9768], "observed_center": [1032, 348]},
        {"name": "joystick", "source_center": [326.3, 794.7], "observed_center": [183, 351]},
    ],
}


class TransformFitTests(unittest.TestCase):
    def test_real_android_five_control_fit(self):
        result = fit_module.fit(REAL_ANDROID_MATCHES)
        self.assertTrue(result["alignment_passed"])
        self.assertEqual(result["matched_count"], 5)
        self.assertAlmostEqual(result["translation_source_units"][1], -200, delta=3)
        self.assertAlmostEqual(result["translation_source_units"][0], 0, delta=3)
        self.assertFalse(result["gameplay_or_original_runtime_parity_proven"])

    def test_outlier_is_detected_without_hiding_it(self):
        data = {**REAL_ANDROID_MATCHES,
                "controls": [dict(row) for row in REAL_ANDROID_MATCHES["controls"]]}
        data["controls"][-1]["observed_center"] = [183, 410]
        result = fit_module.fit(data)
        self.assertFalse(result["alignment_passed"])
        self.assertEqual(result["matched_count"], 4)
        self.assertGreater(result["max_residual_px"], 50)

    def test_rejects_invalid_or_insufficient_points(self):
        with self.assertRaisesRegex(ValueError, "three"):
            fit_module.fit({"source_resolution": [1920,1080],
                            "target_resolution": [1080,640], "controls": []})
        bad = {**REAL_ANDROID_MATCHES,
               "controls": [dict(row) for row in REAL_ANDROID_MATCHES["controls"]]}
        bad["controls"][0]["source_center"] = [float("nan"), 1]
        with self.assertRaisesRegex(ValueError, "invalid coordinates"):
            fit_module.fit(bad)


if __name__ == "__main__":
    unittest.main()
