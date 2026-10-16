"""Regression tests: external backend success can never be EdgeAI native success."""
import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from blind_game_report import summarize

DIGEST = hashlib.sha256(b"ELF synthetic fixture marker").hexdigest()


def inputs():
    build = {
        "binary_sha256": DIGEST, "upstream_repository": "test/game",
        "upstream_commit": "a" * 40, "license": "MIT",
        "eligible_named_functions": 24, "source_used_in_analysis": False,
    }
    edgeai = {
        "file_sha256": DIGEST, "target_executed": False,
        "summary": {
            "functions_selected": 24, "functions_completed": 17,
            "functions_unsupported_or_skipped": 7,
            "table_patterns_in_completed_functions": 2,
        },
    }
    ghidra = {
        "target_source_read": False, "backend": "Ghidra 12.1.3 external decompiler",
        "functions_detected": 25, "pseudocode_functions": 20,
        "functions": [{"status": "GHIDRA_PSEUDOCODE"} for _ in range(20)] +
                     [{"status": "GHIDRA_FAILED"} for _ in range(5)],
    }
    return build, edgeai, ghidra


class BlindGameReportTests(unittest.TestCase):
    def test_counts_are_separated_by_backend(self):
        report = summarize(*inputs(), DIGEST)
        self.assertEqual(report["edgeai_functions_static_audited"], 17)
        self.assertEqual(report["ghidra_pseudocode_functions_including_external_runtime_stubs"], 20)
        self.assertEqual(report["edgeai_native_cpp_functions_recovered"], 0)
        self.assertFalse(report["whole_game_autonomously_decompiled_by_edgeai"])
        self.assertFalse(report["behavioral_equivalence_proven"])
        self.assertTrue(report["requirements_20_to_50_named_functions_met"])

    def test_hash_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, "digest"):
            summarize(*inputs(), "f" * 64)

    def test_source_access_fails(self):
        data = list(inputs())
        data[0]["source_used_in_analysis"] = True
        with self.assertRaisesRegex(ValueError, "source"):
            summarize(*data, DIGEST)

    def test_edgeai_not_executes_game(self):
        data = list(inputs())
        data[1]["target_executed"] = True
        with self.assertRaisesRegex(ValueError, "executed"):
            summarize(*data, DIGEST)

    def test_ghidra_cannot_use_source(self):
        data = list(inputs())
        data[2]["target_source_read"] = True
        with self.assertRaisesRegex(ValueError, "source"):
            summarize(*data, DIGEST)

    def test_bad_external_success_count_fails(self):
        data = list(inputs())
        data[2]["pseudocode_functions"] = 100
        with self.assertRaisesRegex(ValueError, "pseudocode count"):
            summarize(*data, DIGEST)

    def test_functions_count_limit(self):
        data = list(inputs())
        data[1]["summary"]["functions_selected"] = 300
        with self.assertRaisesRegex(ValueError, "invalid audit counts"):
            summarize(*data, DIGEST)

    def test_not_matching_20_50_is_reported_not_hidden(self):
        data = list(inputs())
        data[0]["eligible_named_functions"] = 9
        self.assertFalse(summarize(*data, DIGEST)["requirements_20_to_50_named_functions_met"])


if __name__ == "__main__":
    unittest.main()
