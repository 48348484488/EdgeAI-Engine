import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("measure", ROOT / "scripts" / "measure_low_resource.py")
measure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(measure)


class MeasureLowResourceTests(unittest.TestCase):
    def test_parses_peak_rss(self):
        sample = "Maximum resident set size (kbytes): 12345\n"
        self.assertEqual(measure.parse_peak_rss_bytes(sample), 12345 * 1024)

    def test_missing_rss_fails_closed(self):
        with self.assertRaises(ValueError):
            measure.parse_peak_rss_bytes("elapsed 0.2")

    def test_hard_gates(self):
        good = {"peak_rss_bytes": 64 * 1024 * 1024, "startup_ms": 2000,
                "model_file_bytes": 16 * 1024 * 1024, "threads": 2}
        measure.enforce(good)
        for key, value in (("peak_rss_bytes", 65 * 1024 * 1024),
                           ("startup_ms", 2001),
                           ("model_file_bytes", 16 * 1024 * 1024 + 1),
                           ("threads", 3)):
            bad = dict(good); bad[key] = value
            with self.assertRaises(ValueError):
                measure.enforce(bad)


if __name__ == "__main__":
    unittest.main()
