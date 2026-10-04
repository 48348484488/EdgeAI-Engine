"""Contract tests for the hosted Portuguese v0.17 training smoke job."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.verify_portuguese_training_runs import verify_pair

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/portuguese-v017-training-smoke.yml"


class WorkflowContract(unittest.TestCase):
    def test_hosted_smoke_is_branch_scoped_and_always_uploads_evidence(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for required in (
            "branches: [v0.17-portuguese-neural]",
            "workflow_dispatch:",
            "permissions:\n  contents: read",
            "runs-on: ubuntu-latest",
            "https://download.pytorch.org/whl/cpu",
            "torch==2.10.0",
            "numpy>=1.26,<3",
            "tests.test_portuguese_training_v017.TrainingContracts",
            "tests.test_portuguese_data_v017",
            "--profile quick --threads 1 --out evidence/portuguese-v017-quick-a",
            "--profile quick --threads 1 --out evidence/portuguese-v017-quick-b",
            "status_a=$?",
            "status_b=$?",
            'if [ "$status_a" -ne 0 ] || [ "$status_b" -ne 0 ]; then',
            "verify_portuguese_training_runs.py",
            "if: always()",
            "actions/upload-artifact@v4",
            "evidence/portuguese-v017-quick-a/",
            "evidence/portuguese-v017-quick-b/",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
        self.assertNotIn("selected.edge", text)

    def test_repeatability_verifier_ignores_only_timing_and_checks_checkpoint_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first, second = root / "first", root / "second"
            first.mkdir()
            second.mkdir()
            checkpoint = b"same checkpoint bytes"
            digest = hashlib.sha256(checkpoint).hexdigest()
            for folder, elapsed in ((first, 1.25), (second, 4.5)):
                (folder / "checkpoint-seed-11.pt").write_bytes(checkpoint)
                report = {
                    "protocol": "smoke-1",
                    "seeds": [11],
                    "tokens": {"input": 12, "response": 8},
                    "timing": {"cpu_seconds": elapsed, "wall_seconds": elapsed},
                    "runs": [{"seed": 11, "tokenizer_sha256": "tokenizer-hash",
                              "loss_curve": [{"step": 1, "train_loss": 2.0}]}],
                    "hashes": {"tokenizer": "tokenizer-hash",
                               "artifacts": {"checkpoint-seed-11.pt": digest}},
                }
                (folder / "training.json").write_text(json.dumps(report), encoding="utf-8")

            self.assertEqual(verify_pair(first, second), {"checkpoint-seed-11.pt": digest})

            changed_report = json.loads((second / "training.json").read_text(encoding="utf-8"))
            changed_report["runs"][0]["loss_curve"][0]["train_loss"] = 3.0
            (second / "training.json").write_text(json.dumps(changed_report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "deterministic report"):
                verify_pair(first, second)

            (second / "training.json").write_text(
                (first / "training.json").read_text(encoding="utf-8"), encoding="utf-8")
            (second / "checkpoint-seed-11.pt").write_bytes(b"changed checkpoint bytes")
            with self.assertRaisesRegex(ValueError, "artifact hash"):
                verify_pair(first, second)


if __name__ == "__main__":
    unittest.main()
