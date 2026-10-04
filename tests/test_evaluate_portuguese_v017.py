"""Frozen evaluation contracts: exact counts, review binding and report-only use."""
import copy
import base64
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from evaluate_portuguese_v017 import (
    _run, load_frozen_corpus, main, score_record, summarize, tokenizer_artifact,
)
from portuguese_data_v017 import write_dataset


def evaluation_inputs(root):
    """Independent local input files for report-boundary tests."""
    data = root / "dataset"
    write_dataset(data)
    binary, model = root / "native", root / "model.edge"
    binary.write_bytes(b"native test fixture")
    model.write_bytes(b"EDGEAI5\0" + struct.pack("<5If", 5, 8, 12, 4, 16, 10000.0))
    ledger = root / "reviews.json"
    ledger.write_text(json.dumps({"schema": "edgeai.portuguese.reviews.v1", "reviews": {}}),
                      encoding="utf-8")
    args = ["--binary", str(binary), "--model", str(model), "--corpus", str(data / "test.jsonl"),
            "--manifest", str(data / "manifest.json"), "--reviews", str(ledger),
            "--output", str(root / "report.json")]
    return args, data, ledger


def native_ok(command, **kwargs):
    raw = b'{"route":"neural","neural_used":true,"text":"ok"}\n'
    output = raw.decode(kwargs["encoding"]) if kwargs.get("encoding") else raw
    return subprocess.CompletedProcess(command, 0, output, "" if kwargs.get("encoding") else b"")


class PortugueseEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.item = {"id": "open-1", "category": "greeting", "prompt": "Olá!",
                     "response": "Olá! Como posso ajudar?"}
        self.response = {"route": "neural", "neural_used": True,
                         "text": "Olá! Como posso ajudar?"}
        self.review = {"open-1": {"decision": "pass", "reviewer": "human-test",
                                 "response_sha256": hashlib.sha256(
                                     self.response["text"].encode("utf-8")).hexdigest()}}

    def test_open_answer_defaults_to_failure_even_when_equal_to_reference(self):
        record = score_record(self.item, self.response, {})
        self.assertFalse(record["passed"])
        self.assertTrue(record["exact_match"])
        self.assertFalse(record["reviewed"])
        self.assertEqual(record["scoring_mode"], "human_review")

    def test_hash_bound_human_approval_passes_without_mutating_ledger(self):
        before = copy.deepcopy(self.review)
        record = score_record(self.item, self.response, self.review)
        self.assertTrue(record["passed"])
        self.assertTrue(record["reviewed"])
        self.assertEqual(self.review, before)
        self.assertEqual(record["response"], self.response)

    def test_changed_response_invalidates_review_without_normalizing_its_hash(self):
        for text in ("changed", self.response["text"] + " "):
            with self.subTest(text=text):
                record = score_record(self.item, dict(self.response, text=text), self.review)
                self.assertFalse(record["passed"])
                self.assertFalse(record["reviewed"])

    def test_rejection_is_reviewed_but_never_approved(self):
        self.review["open-1"]["decision"] = "fail"
        record = score_record(self.item, self.response, self.review)
        self.assertTrue(record["reviewed"])
        self.assertFalse(record["passed"])

    def test_malformed_decision_or_missing_reviewer_cannot_approve(self):
        for field, value in (("decision", True), ("decision", "PASS"),
                             ("reviewer", ""), ("reviewer", None)):
            with self.subTest(field=field, value=value):
                reviews = copy.deepcopy(self.review)
                reviews["open-1"][field] = value
                self.assertFalse(score_record(self.item, self.response, reviews)["passed"])

    def test_empty_and_nonstring_outputs_fail_even_with_approval(self):
        for text in ("", " \t\n", None, 123):
            with self.subTest(text=text):
                record = score_record(self.item, dict(self.response, text=text), self.review)
                self.assertFalse(record["passed"])
                self.assertTrue(record["malformed"])

    def test_surrogate_text_is_malformed_and_cannot_receive_a_hash_or_approval(self):
        for text in ("\ud800", "\udfff"):
            with self.subTest(text=repr(text)):
                record = score_record(self.item, dict(self.response, text=text), self.review)
                self.assertFalse(record["passed"])
                self.assertTrue(record["malformed"])
                self.assertFalse(record["reviewed"])
                self.assertIsNone(record["response_sha256"])

    def test_invalid_unicode_records_retain_bytes_and_report_continues(self):
        invalid = b'{"route":"neural","neural_used":true,"text":"\xff"}\n'
        surrogate = b'{"route":"neural","neural_used":true,"text":"\\ud800"}\n'
        count = 0
        def native_run(command, **kwargs):
            nonlocal count
            count += 1
            raw = invalid if count == 1 else surrogate if count == 2 else (
                b'{"route":"neural","neural_used":true,"text":"ok"}\n')
            # Faithfully reproduce the existing strict text-mode subprocess
            # behavior, while allowing the fixed evaluator to capture bytes.
            output = raw.decode(kwargs["encoding"]) if kwargs.get("encoding") else raw
            return subprocess.CompletedProcess(command, 0, output, b"")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args, _, _ = evaluation_inputs(root)
            with patch("evaluate_portuguese_v017.subprocess.run", side_effect=native_run):
                self.assertEqual(main(args), 0)
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(len(report["records"]), 60)
        for record, raw in zip(report["records"][:2], (invalid, surrogate)):
            self.assertTrue(record["malformed"])
            self.assertFalse(record["passed"])
            self.assertFalse(record["reviewed"])
            self.assertIsNone(record["response_sha256"])
            self.assertEqual(base64.b64decode(record["stdout_bytes_base64"]), raw)

    def test_ledger_edit_after_parsing_cannot_rebind_approval_to_new_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args, data, ledger = evaluation_inputs(root)
            row = next(row for row in map(json.loads, (data / "test.jsonl").read_bytes().splitlines())
                       if row["category"] == "greeting")
            approval = {row["id"]: {"decision": "pass", "reviewer": "human-test",
                                     "response_sha256": hashlib.sha256(b"ok").hexdigest()}}
            ledger.write_text(json.dumps({"schema": "edgeai.portuguese.reviews.v1", "reviews": approval}),
                              encoding="utf-8")
            parse = json.loads
            edited = False
            def parse_and_edit(raw, *extra, **kwargs):
                nonlocal edited
                parsed = parse(raw, *extra, **kwargs)
                if isinstance(parsed, dict) and parsed.get("schema") == "edgeai.portuguese.reviews.v1" and not edited:
                    edited = True
                    ledger.write_text(json.dumps({"schema": "edgeai.portuguese.reviews.v1", "reviews": {}}),
                                      encoding="utf-8")
                return parsed
            with patch("evaluate_portuguese_v017.json.loads", side_effect=parse_and_edit), \
                 patch("evaluate_portuguese_v017.subprocess.run", side_effect=native_ok):
                with self.assertRaisesRegex(ValueError, "input changed.*reviews"):
                    main(args)
            self.assertTrue(edited)
            self.assertFalse((root / "report.json").exists())

    def test_corpus_edit_after_validation_cannot_be_hashed_as_scored_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args, data, _ = evaluation_inputs(root)
            def validate_and_edit(corpus, manifest):
                loaded = load_frozen_corpus(corpus, manifest)
                corpus.write_bytes(corpus.read_bytes() + b"\n")
                return loaded
            with patch("evaluate_portuguese_v017.load_frozen_corpus", side_effect=validate_and_edit), \
                 patch("evaluate_portuguese_v017.subprocess.run", side_effect=native_ok):
                with self.assertRaisesRegex(ValueError, "input changed.*corpus"):
                    main(args)
            self.assertFalse((root / "report.json").exists())

    def test_wrong_route_or_missing_neural_flag_cannot_pass_review(self):
        for response in (dict(self.response, route="text_copy"),
                         dict(self.response, neural_used=False),
                         dict(self.response, neural_used=1)):
            with self.subTest(response=response):
                self.assertFalse(score_record(self.item, response, self.review)["passed"])

    def test_closed_facts_require_normalized_exact_text_and_neural_route(self):
        item = dict(self.item, category="closed_fact", response="Março.")
        for text, passed in ((" Março.\n", True), ("Marc\u0327o.", True),
                             ("março.", False), ("Março", False), ("Abril.", False)):
            with self.subTest(text=text):
                record = score_record(item, dict(self.response, text=text), {})
                self.assertEqual(record["passed"], passed)
                self.assertEqual(record["scoring_mode"], "exact")
                self.assertFalse(record["reviewed"])
        self.assertFalse(score_record(item, dict(self.response, text="Março.",
                                                 route="text_copy"), {})["passed"])

    def test_fluent_short_instruction_is_open_and_needs_review(self):
        item = dict(self.item, category="short_instruction",
                    prompt="Escreva um pedido educado de um café.",
                    response="Por favor, gostaria de um café.")
        response = dict(self.response, text=item["response"])
        self.assertFalse(score_record(item, response, {})["passed"])
        self.assertEqual(score_record(item, response, {})["scoring_mode"], "human_review")

    def test_tool_exact_answers_remain_separate_and_require_route(self):
        item = {"id": "calc-1", "category": "tool", "prompt": "2+2",
                "expected_route": "calculator", "expected_text": "4"}
        self.assertTrue(score_record(item, {"text": "4", "route": "calculator",
                                           "neural_used": False}, {})["passed"])
        for response in ({"text": "5", "route": "calculator"},
                         {"text": "4", "route": "neural", "neural_used": True}):
            self.assertFalse(score_record(item, response, {})["passed"])

    def test_unknown_category_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "category"):
            score_record(dict(self.item, category="unknown"), self.response, {})

    def test_summary_reports_exact_denominators_by_category_and_scoring_mode(self):
        records = [score_record(self.item, self.response, self.review),
                   score_record(dict(self.item, id="open-2"), self.response, {}),
                   score_record(dict(self.item, id="fact-1", category="closed_fact"),
                                self.response, {}),
                   score_record({"id": "calc", "category": "tool", "prompt": "2+2",
                                 "expected_route": "calculator", "expected_text": "4"},
                                {"text": "4", "route": "calculator"}, {})]
        summary = summarize(records)
        self.assertEqual(summary["neural"]["passed"], 2)
        self.assertEqual(summary["neural"]["total"], 3)
        self.assertEqual(summary["neural"]["reviewed"], 1)
        self.assertEqual(summary["neural"]["exact_passed"], 1)
        self.assertEqual(summary["neural"]["human_review_passed"], 1)
        self.assertEqual(summary["categories"]["greeting"]["passed"], 1)
        self.assertEqual(summary["categories"]["greeting"]["total"], 2)
        self.assertEqual(summary["tool"], {"passed": 1, "total": 1, "rate": 1.0})
        self.assertNotIn("accuracy", summary)
        self.assertFalse(summary["checkpoint_selection_allowed"])

    def test_empty_summary_is_explicit_zero_denominators(self):
        summary = summarize([])
        self.assertEqual(summary["neural"]["total"], 0)
        self.assertEqual(summary["neural"]["rate"], 0.0)
        self.assertEqual(summary["malformed"]["total"], 0)

    def test_runtime_timeout_is_a_failed_record_with_retained_partial_output(self):
        with patch("evaluate_portuguese_v017.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(["native"], 30,
                                                         output=b"partial", stderr=b"timeout detail")):
            record = _run("native", "model", self.item, {})
        self.assertFalse(record["passed"])
        self.assertTrue(record["malformed"])
        self.assertEqual(record["stdout"], "partial")
        self.assertEqual(record["stderr"], "timeout detail")
        self.assertTrue(any("timeout" in note for note in record["notes"]))

    def test_invalid_stderr_is_diagnostic_and_does_not_reject_valid_stdout(self):
        item = {"id": "calc", "category": "tool", "prompt": "2+2",
                "expected_route": "calculator", "expected_text": "4"}
        stdout = b'{"route":"calculator","neural_used":false,"text":"4"}\n'
        stderr = b"diagnostic: \xff\n"
        process = subprocess.CompletedProcess([], 0, stdout, stderr)
        with patch("evaluate_portuguese_v017.subprocess.run", return_value=process):
            record = _run("native", "model", item, {})
        self.assertTrue(record["passed"])
        self.assertFalse(record["malformed"])
        self.assertEqual(record["text"], "4")
        self.assertFalse(record["stderr_utf8_valid"])
        self.assertEqual(base64.b64decode(record["stderr_bytes_base64"]), stderr)
        self.assertTrue(any("stderr" in note and "UTF-8" in note for note in record["notes"]))

    def test_output_cannot_overwrite_another_sealed_dataset_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_dataset(root)
            protected = root / "train.jsonl"
            before = protected.read_bytes()
            with self.assertRaisesRegex(ValueError, "overwrite"):
                main(["--binary", "missing", "--model", "missing",
                      "--corpus", str(root / "test.jsonl"), "--manifest", str(root / "manifest.json"),
                      "--reviews", "missing", "--output", str(protected)])
            self.assertEqual(protected.read_bytes(), before)

    def test_only_verified_frozen_test_corpus_can_be_evaluated(self):
        root = ROOT / "data/portuguese_v017"
        rows, _ = load_frozen_corpus(root / "test.jsonl", root / "manifest.json")
        self.assertEqual(len(rows), 40)
        for split in ("train", "valid"):
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, "test"):
                load_frozen_corpus(root / (split + ".jsonl"), root / "manifest.json")

    def test_cli_refuses_checkpoint_selection_before_running_a_model(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/evaluate_portuguese_v017.py"),
                                 "--select-checkpoint", "--binary", "missing", "--model", "missing",
                                 "--corpus", "missing", "--manifest", "missing", "--reviews", "missing",
                                 "--output", "missing"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments: --select-checkpoint", result.stderr)

    def test_tokenizer_hash_binds_mode_and_merges_independently_of_weights(self):
        header = b"EDGEAI7\0" + struct.pack("<5IfI", 7, 8, 12, 4, 16, 10000.0, 1)
        one = tokenizer_artifact(header + struct.pack("<2I", 65, 66) + b"weights-A")
        two = tokenizer_artifact(header + struct.pack("<2I", 65, 66) + b"weights-B")
        three = tokenizer_artifact(header + struct.pack("<2I", 65, 67) + b"weights-A")
        self.assertEqual(one["sha256"], two["sha256"])
        self.assertNotEqual(one["sha256"], three["sha256"])
        self.assertEqual(one["mode"], 2)
        self.assertEqual(one["merge_count"], 1)
        with self.assertRaisesRegex(ValueError, "tokenizer"):
            tokenizer_artifact(header + b"short")

    def test_cli_reports_outputs_hashes_and_comparison_without_changing_reviews(self):
        # Only the native process is replaced: this covers real corpus verification,
        # scoring, ledger reading, comparison and report persistence.
        corpus = ROOT / "data/portuguese_v017/test.jsonl"
        rows = [json.loads(line) for line in corpus.read_text(encoding="utf-8").splitlines()]
        answers = {row["prompt"]: row["response"] for row in rows}
        tools = [json.loads(line) for line in (ROOT / "data/low_resource_v016/prompts.jsonl")
                 .read_text(encoding="utf-8").splitlines()]
        tools = {row["prompt"]: row for row in tools if row["category"] == "tool"}
        def native_run(command, **kwargs):
            prompt = command[command.index("--prompt") + 1]
            item = tools.get(prompt)
            response = {"route": item["expected_route"] if item else "neural",
                        "neural_used": item is None,
                        "text": item["expected_text"] if item else answers[prompt]}
            raw = (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")
            output = raw.decode(kwargs["encoding"]) if kwargs.get("encoding") else raw
            return subprocess.CompletedProcess(command, 0, output, "" if kwargs.get("encoding") else b"")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary, model = root / "native", root / "model.edge"
            binary.write_bytes(b"native test fixture")
            model.write_bytes(b"EDGEAI5\0" + struct.pack("<5If", 5, 8, 12, 4, 16, 10000.0))
            reviews = root / "reviews.json"
            reviews.write_text(json.dumps({"schema": "edgeai.portuguese.reviews.v1", "reviews": {}}),
                               encoding="utf-8")
            before = reviews.read_bytes()
            output = root / "report.json"
            args = ["--binary", str(binary), "--model", str(model), "--corpus", str(corpus),
                    "--manifest", str(corpus.with_name("manifest.json")), "--reviews", str(reviews),
                    "--output", str(output)]
            with patch("evaluate_portuguese_v017.subprocess.run", side_effect=native_run):
                self.assertEqual(main(args), 0)
                control = root / "control.json"
                control.write_bytes(output.read_bytes())
                self.assertEqual(main(args + ["--compare-control", str(control)]), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["neural"]["passed"], 10)
            self.assertEqual(report["neural"]["total"], 40)
            self.assertEqual(report["neural"]["human_review_passed"], 0)
            self.assertEqual(report["tool"]["passed"], 20)
            self.assertEqual(len(report["records"]), 60)
            self.assertEqual(report["artifacts"]["reviews"]["sha256"], hashlib.sha256(before).hexdigest())
            self.assertEqual(reviews.read_bytes(), before)
            self.assertEqual(report["comparison"]["neural_pass_delta"], 0)
            self.assertFalse(report["checkpoint_selection_allowed"])
            self.assertEqual(report["historical_v016_neural"], {"passed": 0, "total": 20})
            self.assertTrue(all("response" in r and "stdout" in r for r in report["records"]))
            self.assertEqual(report["artifacts"]["model"]["sha256"],
                             hashlib.sha256(model.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
