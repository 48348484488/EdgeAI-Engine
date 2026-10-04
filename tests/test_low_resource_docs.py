import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DocumentationContract(unittest.TestCase):
    def test_readme_states_scope_limits_and_honest_baseline(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for token in ("64 MiB", "16 MiB", "CPU-only", "EDGEAI_LOW_RESOURCE", "tool accuracy", "neural"):
            self.assertIn(token, text)
        self.assertIn("does not claim parity", text.lower())
        self.assertLess(len(text.splitlines()), 180)

    def test_detailed_runtime_document_exists(self):
        text = (ROOT / "docs/low-resource-runtime.md").read_text(encoding="utf-8")
        self.assertIn("Fail-fast behavior", text)
        self.assertIn("Evidence", text)


if __name__ == "__main__":
    unittest.main()
