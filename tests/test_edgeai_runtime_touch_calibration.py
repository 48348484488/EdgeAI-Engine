import unittest
from tools.edgeai_ui_transform_fit import calibrate_runtime_touch

SAMPLE = {
    "source_resolution": [1920, 1080],
    "logical_resolution": [1280, 720],
    "physical_resolution": [1080, 640],
    "source_visual_offset": [0, -200],
    "observed_source_touch": [1246.2, 976.2],
    "observed_physical_touch": [701, 454],
    "logical_hitboxes": {
        "foundation": [505.45, 486.08, 568.61, 549.42],
        "place": [1001.06, 316.46, 1122.40, 437.80],
    },
}


class RuntimeTouchCalibrationTests(unittest.TestCase):
    def test_real_android_letterboxed_touch(self):
        result = calibrate_runtime_touch(SAMPLE)
        self.assertAlmostEqual(result["physical_scale"], 0.84375)
        self.assertAlmostEqual(result["physical_origin"][0], 0.013, places=2)
        self.assertAlmostEqual(result["physical_origin"][1], 17.387, places=2)
        x, y = result["physical_hitbox_centers"]["foundation"]
        self.assertAlmostEqual(x, 453.1, delta=1)
        self.assertAlmostEqual(y, 454.2, delta=1)
        self.assertFalse(result["original_game_parity_proven"])

    def test_missing_source_offset_changes_calibration(self):
        d = dict(SAMPLE, source_visual_offset=[0, 0])
        result = calibrate_runtime_touch(d)
        self.assertNotAlmostEqual(result["physical_origin"][1], 17.387, places=1)

    def test_reject_zero_resolution(self):
        with self.assertRaises(ValueError):
            calibrate_runtime_touch(dict(SAMPLE, physical_resolution=[0, 640]))

    def test_reject_bad_hitbox(self):
        with self.assertRaises(ValueError):
            calibrate_runtime_touch(dict(SAMPLE, logical_hitboxes={"bad": [10, 20, 5, 25]}))

    def test_reject_nonfinite_touch(self):
        with self.assertRaises(ValueError):
            calibrate_runtime_touch(dict(SAMPLE, observed_physical_touch=[float("nan"), 0]))


if __name__ == "__main__":
    unittest.main()
