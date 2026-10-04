"""Contracts for licensed, reproducible Portuguese data and sealed test inputs."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from portuguese_data_v017 import (
    build_dataset, load_dataset, normalize_text, training_rows, training_texts,
    validate_dataset, validate_sources, write_dataset,
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


class PortugueseDataTests(unittest.TestCase):
    def setUp(self):
        self.sources = json.loads((ROOT / "data/portuguese_v017/sources.json")
                                  .read_text(encoding="utf-8"))

    def test_missing_license_is_rejected(self):
        sources = copy.deepcopy(self.sources)
        del sources[0]["license"]
        with self.assertRaisesRegex(ValueError, "license"):
            validate_sources(sources)

    def test_unknown_license_is_rejected(self):
        sources = copy.deepcopy(self.sources)
        sources[0]["license"] = "LicenseRef-unknown"
        with self.assertRaisesRegex(ValueError, "license"):
            validate_sources(sources)

    def test_missing_origin_method_or_content_hash_is_rejected(self):
        for field in ("origin", "method", "content_sha256"):
            with self.subTest(field=field):
                sources = copy.deepcopy(self.sources)
                del sources[0][field]
                with self.assertRaises(ValueError):
                    validate_sources(sources)

    def test_changed_source_content_is_rejected(self):
        sources = copy.deepcopy(self.sources)
        sources[0]["content"]["templates"]["greeting"][0] += " altered"
        with self.assertRaisesRegex(ValueError, "hash"):
            validate_sources(sources)

    def test_duplicate_source_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_sources(self.sources + self.sources[:1])

    def test_nfc_accents_and_whitespace_normalize(self):
        self.assertEqual(normalize_text("ac\u0327a\u0303o"), "ação")
        self.assertEqual(normalize_text("  ação\r\n curta\t "), "ação curta")

    def test_ids_bind_the_normalized_complete_record(self):
        data = build_dataset()
        ids = []
        for rows in data.values():
            for row in rows:
                identity = {key: value for key, value in row.items() if key != "id"}
                self.assertEqual(row["id"], hashlib.sha256(canonical(identity)).hexdigest())
                ids.append(row["id"])
                self.assertEqual(set(row), {"id", "category", "prompt", "response",
                                           "source_id", "license"})
        self.assertEqual(len(ids), len(set(ids)))

    def test_registry_hashes_and_row_provenance_are_verifiable(self):
        registry = {source["source_id"]: source for source in self.sources}
        validate_sources(self.sources)
        for source in self.sources:
            self.assertEqual(source["content_sha256"],
                             hashlib.sha256(canonical(source["content"])).hexdigest())
        for rows in build_dataset().values():
            for row in rows:
                self.assertEqual(row["license"], registry[row["source_id"]]["license"])

    def test_builds_are_identical_and_test_is_balanced(self):
        first, second = build_dataset(), build_dataset()
        self.assertEqual(canonical(first), canonical(second))
        self.assertEqual(set(first), {"train", "valid", "test"})
        self.assertEqual(Counter(row["category"] for row in first["test"]),
                         {"greeting": 10, "definition": 10, "closed_fact": 10,
                          "short_instruction": 10})
        self.assertTrue(first["train"])
        self.assertTrue(first["valid"])

    def test_decomposed_prompt_cannot_cross_train_test(self):
        data = build_dataset()
        data["train"][0]["prompt"] = "Explique a ação."
        data["test"][0]["prompt"] = "Explique a ac\u0327a\u0303o."
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_dataset(data)

    def test_cosmetic_prompt_variants_cannot_cross_splits(self):
        for variant in (" EXPLIQUE  A AÇÃO. ", "Explique a ação!", "explique a ação"):
            with self.subTest(variant=variant):
                data = build_dataset()
                data["train"][0]["prompt"] = "Explique a ação."
                data["valid"][0]["prompt"] = variant
                with self.assertRaisesRegex(ValueError, "overlap"):
                    validate_dataset(data)

    def test_answer_bearing_records_cannot_cross_splits(self):
        data = build_dataset()
        data["test"].append(copy.deepcopy(data["train"][0]))
        with self.assertRaises(ValueError):
            validate_dataset(data)

    def test_wrong_row_source_and_license_are_rejected(self):
        for field, value in (("source_id", "not-registered"), ("license", "MIT")):
            with self.subTest(field=field):
                data = build_dataset()
                data["train"][0][field] = value
                with self.assertRaises(ValueError):
                    validate_dataset(data)

    def test_tokenizer_and_training_inputs_exclude_valid_and_test(self):
        data = build_dataset()
        rows = training_rows(data)
        self.assertEqual(rows, data["train"])
        texts = training_texts(data)
        self.assertEqual(texts, [text for row in data["train"]
                                 for text in (row["prompt"], row["response"])])
        joined = "\n".join(texts)
        for split in ("valid", "test"):
            for row in data[split]:
                self.assertNotIn(row["prompt"], joined)
        rows[0]["prompt"] = "changed by consumer"
        self.assertNotEqual(rows[0]["prompt"], data["train"][0]["prompt"])

    def test_training_rows_rejects_reassigned_holdouts(self):
        for split in ("valid", "test"):
            with self.subTest(split=split):
                data = build_dataset()
                data["train"][0], data[split][0] = data[split][0], data["train"][0]
                with self.assertRaisesRegex(ValueError, "sealed"):
                    training_rows(data)

    def test_training_texts_rejects_reassigned_holdouts(self):
        for split in ("valid", "test"):
            with self.subTest(split=split):
                data = build_dataset()
                data["train"][0], data[split][0] = data[split][0], data["train"][0]
                with self.assertRaisesRegex(ValueError, "sealed"):
                    training_texts(data)

    def test_closed_fact_test_answers_have_independent_training_support(self):
        data = build_dataset()
        facts = [row for row in data["test"] if row["category"] == "closed_fact"]
        responses = {row["response"] for row in data["train"] if row["category"] == "closed_fact"}
        unsupported = [row["response"] for row in facts if row["response"] not in responses]
        self.assertFalse(unsupported, "closed facts missing training knowledge: " + repr(unsupported))
        support = [row for row in data["train"] if row["source_id"] == "supporting-facts-v017"]
        self.assertEqual(len(support), 40)
        self.assertTrue(all(any(row["response"] == fact["response"] for row in support) for fact in facts))
        source = next(row for row in self.sources if row["source_id"] == "supporting-facts-v017")
        self.assertIs(source["content"]["training_only"], True)
        self.assertFalse(any(row["source_id"] == source["source_id"]
                             for split in ("valid", "test") for row in data[split]))
        self.assertIn({"category": "closed_fact", "key": "knowledge-00",
                       "prompt": "Complete a informação: o ano começa no mês de...",
                       "response": "Janeiro."}, source["content"]["records"])

    def test_sealed_files_have_lf_sorted_keys_and_verified_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = write_dataset(root)
            loaded, loaded_manifest = load_dataset(root)
            self.assertEqual(loaded, build_dataset())
            self.assertEqual(manifest, loaded_manifest)
            self.assertEqual(manifest["tokenizer_splits"], ["train"])
            self.assertEqual(manifest["training_splits"], ["train"])
            self.assertEqual(manifest["selection_splits"], ["valid"])
            self.assertEqual(manifest["sealed_splits"], ["test"])
            for filename, record in manifest["files"].items():
                raw = (root / filename).read_bytes()
                self.assertNotIn(b"\r", raw)
                self.assertTrue(raw.endswith(b"\n"))
                self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(record["bytes"], len(raw))
                if filename.endswith(".jsonl"):
                    self.assertEqual(record["rows"], len(raw.splitlines()))
                    for line in raw.splitlines():
                        self.assertEqual(line, canonical(json.loads(line)))

    def test_regeneration_is_byte_identical_including_manifest(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a, b = Path(first), Path(second)
            write_dataset(a)
            before = {path.name: path.read_bytes() for path in a.iterdir()}
            write_dataset(a)
            write_dataset(b)
            self.assertEqual(before, {path.name: path.read_bytes() for path in a.iterdir()})
            self.assertEqual(before, {path.name: path.read_bytes() for path in b.iterdir()})

    def test_loader_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_dataset(root)
            path = root / "test.jsonl"
            path.write_bytes(path.read_bytes() + b"{}\n")
            with self.assertRaisesRegex(ValueError, "hash"):
                load_dataset(root)

    def test_loader_rejects_training_policy_or_generator_drift(self):
        for field, value in (("training_splits", ["train", "test"]),
                             ("generator_sha256", "0" * 64)):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = write_dataset(root)
                manifest[field] = value
                (root / "manifest.json").write_bytes(canonical(manifest) + b"\n")
                with self.assertRaises(ValueError):
                    load_dataset(root)

    def test_rehashed_split_reassignment_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = write_dataset(root)
            data, _ = load_dataset(root)
            data["train"][0], data["test"][0] = data["test"][0], data["train"][0]
            for split in ("train", "test"):
                raw = b"".join(canonical(row) + b"\n" for row in data[split])
                name = split + ".jsonl"
                (root / name).write_bytes(raw)
                manifest["files"][name].update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            (root / "manifest.json").write_bytes(canonical(manifest) + b"\n")
            with self.assertRaisesRegex(ValueError, "sealed"):
                load_dataset(root)

    def test_writer_refuses_to_overwrite_changed_sealed_splits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_dataset(root)
            path = root / "test.jsonl"
            changed = path.read_bytes() + b"{}\n"
            path.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "sealed"):
                write_dataset(root)
            self.assertEqual(path.read_bytes(), changed)

    def test_cli_regenerates_committed_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, str(ROOT / "tools/portuguese_data_v017.py"),
                                     "--out", directory], capture_output=True, check=True)
            self.assertEqual(json.loads(result.stdout)["sealed_splits"], ["test"])
            root = ROOT / "data/portuguese_v017"
            for generated in Path(directory).iterdir():
                self.assertEqual(generated.read_bytes(), (root / generated.name).read_bytes())


if __name__ == "__main__":
    unittest.main()
