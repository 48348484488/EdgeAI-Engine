import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from edgeai_runtime_stage_audit import audit

SPEC = {"stages": [{"name": "boot", "pattern": "BOOT"},
                    {"name": "graphics", "pattern": "GRAPHICS"},
                    {"name": "frame", "pattern": "FRAME_DONE"}]}

class RuntimeStageTests(unittest.TestCase):
    def test_success(self):
        result = audit("10-31 11:00:00.000 BOOT\n10-31 11:00:01.000 GRAPHICS\n10-31 11:00:02.000 FRAME_DONE", SPEC)
        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["render_verified"])
    def test_stall_and_elapsed(self):
        result = audit("10-31 11:00:00.000 BOOT\n10-31 11:00:01.000 GRAPHICS\n10-31 11:01:10.000 OTHER", SPEC)
        self.assertEqual(result["next_stage"], "frame")
        self.assertEqual(result["seconds_since_last_stage"], 69)
        self.assertFalse(result["render_verified"])
    def test_out_of_order_not_accepted(self):
        result = audit("10-31 11:00:00.000 FRAME_DONE\n10-31 11:00:01.000 BOOT", SPEC)
        self.assertEqual(result["last_stage"], "boot")
    def test_duplicate_names(self):
        with self.assertRaises(ValueError):
            audit("", {"stages": [{"name":"x","pattern":"x"},{"name":"x","pattern":"y"}]})
    def test_invalid_timestamp(self):
        result = audit("bad BOOT\nbad GRAPHICS\nbad FRAME_DONE", SPEC)
        self.assertEqual(result["status"], "complete")
        self.assertIsNone(result["seconds_since_last_stage"])
    def test_optional_stage_skipped_when_later_required_is_seen(self):
        spec = {"stages": [{"name":"boot","pattern":"BOOT"},
                           {"name":"optional_input","pattern":"INPUT","optional":True},
                           {"name":"frame","pattern":"FRAME_DONE"}]}
        result = audit("10-31 11:00:00.000 BOOT\n10-31 11:00:01.000 FRAME_DONE", spec)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["skipped_optional_stages"], ["optional_input"])
    def test_empty_manifest(self):
        with self.assertRaises(ValueError):
            audit("", {"stages": []})

if __name__ == '__main__':
    unittest.main()
