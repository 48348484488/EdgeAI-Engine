"""Licensed, sealed Portuguese v0.17 diagnostic corpus; no network or RNG.

Tokenizer and training consumers must use training_rows/training_texts, never
the source registry (which includes held-out seed pairs). Common response labels
may repeat; seed groups and normalized prompts never cross split boundaries.
"""
import argparse
import copy
import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "data/portuguese_v017"
SPLITS = ("train", "valid", "test")
CATEGORIES = ("greeting", "definition", "closed_fact", "short_instruction")
LICENSE_ALLOWLIST = frozenset({"CC0-1.0"})
FORMAT = "edge-portuguese-v017-1"
SPLIT_POLICY = "edge-portuguese-v017-seed-rank-1"
ROW_FIELDS = frozenset({"id", "category", "prompt", "response", "source_id", "license"})


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def normalize_text(value: str) -> str:
    """NFC text with whitespace runs folded to one space; preserve accents/case."""
    if not isinstance(value, str):
        raise ValueError("text must be a string")
    return " ".join(unicodedata.normalize("NFC", value).split())


def _prompt_key(value):
    # Prevent punctuation/case/spacing-only leakage without stripping accents.
    return " ".join(re.findall(r"\w+", normalize_text(value).casefold()))


def validate_sources(rows: list[dict]) -> None:
    """Validate source licenses, provenance and hashes of redistributed content."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty or invalid source registry")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid source")
        if row.get("license") not in LICENSE_ALLOWLIST:
            raise ValueError("missing or non-allowlisted source license")
        for field in ("source_id", "origin", "method", "content_sha256"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError("missing source " + field)
        if row["source_id"] in seen:
            raise ValueError("duplicate source_id")
        seen.add(row["source_id"])
        content = row.get("content")
        if not isinstance(content, dict) or not content.get("records"):
            raise ValueError("missing source content")
        if row["content_sha256"] != _sha(_canonical(content)):
            raise ValueError("source content hash mismatch")
        keys = set()
        for record in content["records"]:
            for field in ("key", "category", "prompt", "response"):
                if not isinstance(record.get(field), str) or not normalize_text(record[field]):
                    raise ValueError("invalid source record " + field)
            if record["category"] not in CATEGORIES or record["key"] in keys:
                raise ValueError("unknown category or duplicate source record key")
            keys.add(record["key"])


def _sources():
    rows = json.loads((SOURCE_ROOT / "sources.json").read_text(encoding="utf-8"))
    validate_sources(rows)
    return rows


def validate_dataset(data: dict[str, list[dict]]) -> None:
    """Reject schema/provenance drift and normalized cross-split contamination."""
    if set(data) != set(SPLITS):
        raise ValueError("missing or unknown split")
    seen_prompts, seen_records = {}, {}
    # Check overlap first so a normalized duplicate cannot hide behind its ID.
    for split in SPLITS:
        if not isinstance(data[split], list) or not data[split]:
            raise ValueError("empty or invalid split: " + split)
        for row in data[split]:
            if not isinstance(row, dict) or set(row) != ROW_FIELDS:
                raise ValueError("invalid dataset row schema")
            if any(not isinstance(value, str) or not normalize_text(value)
                   for value in row.values()):
                raise ValueError("empty or invalid dataset row field")
            key = _prompt_key(row["prompt"])
            if not key or key in seen_prompts:
                raise ValueError("normalized prompt overlap: " + split)
            seen_prompts[key] = split
            record_key = (normalize_text(row["prompt"]), normalize_text(row["response"]))
            if record_key in seen_records:
                raise ValueError("answer-bearing record overlap")
            seen_records[record_key] = split
    registry = {row["source_id"]: row for row in _sources()}
    seen_ids = set()
    for split in SPLITS:
        for row in data[split]:
            source = registry.get(row["source_id"])
            if source is None or row["license"] != source["license"]:
                raise ValueError("unregistered source or mismatched license")
            if row["category"] not in CATEGORIES:
                raise ValueError("unknown category")
            if any(normalize_text(row[field]) != row[field] for field in ROW_FIELDS):
                raise ValueError("row text must be normalized")
            identity = {key: value for key, value in row.items() if key != "id"}
            if row["id"] != _sha(_canonical(identity)) or row["id"] in seen_ids:
                raise ValueError("invalid or duplicate SHA-256 row id")
            seen_ids.add(row["id"])
    if data != _generate_dataset():
        raise ValueError("sealed split assignment or content differs from the generator")


def _generate_dataset() -> dict[str, list[dict]]:
    """Rank 40 seed groups/category once; keep all variants in their seed split."""
    sources = _sources()
    templates = sources[0]["content"]["templates"]
    result = {split: [] for split in SPLITS}
    for category in CATEGORIES:
        seeds = [(source, record) for source in sources if not source["content"].get("training_only", False)
                 for record in source["content"]["records"] if record["category"] == category]
        if len(seeds) != 40:
            raise ValueError("sealed v0.17 requires 40 seed groups per category")
        seeds.sort(key=lambda pair: _sha((SPLIT_POLICY + ":" + category + ":" +
                                          pair[1]["key"]).encode("utf-8")))
        for index, (source, seed) in enumerate(seeds):
            split = "test" if index < 10 else "valid" if index < 15 else "train"
            variants = templates[category] if split == "train" else templates[category][:1]
            for template in variants:
                row = dict(category=category, prompt=normalize_text(template.format(prompt=seed["prompt"])),
                           response=normalize_text(seed["response"]), source_id=source["source_id"],
                           license=source["license"])
                row["id"] = _sha(_canonical(row))
                result[split].append(row)
    # Independent supporting facts are registered for train before any model
    # run. Do not synthesize these from held-out prompts or their target labels.
    for source in sources:
        if source["content"].get("training_only", False):
            for seed in source["content"]["records"]:
                row = dict(category=seed["category"], prompt=normalize_text(seed["prompt"]),
                           response=normalize_text(seed["response"]), source_id=source["source_id"],
                           license=source["license"])
                row["id"] = _sha(_canonical(row))
                result["train"].append(row)
    for rows in result.values():
        rows.sort(key=lambda row: row["id"])
    return result


def build_dataset() -> dict[str, list[dict]]:
    """Build and validate the sealed seed splits and independent train facts."""
    result = _generate_dataset()
    validate_dataset(result)
    return result


def training_rows(data=None) -> list[dict]:
    """Return independent train rows only; validation/test never become inputs."""
    data = build_dataset() if data is None else data
    validate_dataset(data)
    return copy.deepcopy(data["train"])


def training_texts(data=None) -> list[str]:
    """Tokenizer text and supervised inputs: train prompts/responses only."""
    return [text for row in training_rows(data) for text in (row["prompt"], row["response"])]


def write_dataset(root: Path) -> dict:
    """Generate canonical UTF-8/LF data and bind all redistributable input files."""
    root = Path(root)
    data = build_dataset()
    payloads = {split + ".jsonl": b"".join(_canonical(row) + b"\n" for row in data[split])
                for split in SPLITS}
    payloads.update({name: (SOURCE_ROOT / name).read_bytes() for name in ("sources.json", "NOTICE.md")})
    files = {name: dict(sha256=_sha(raw), bytes=len(raw)) for name, raw in payloads.items()}
    for split in SPLITS:
        files[split + ".jsonl"]["rows"] = len(data[split])
    manifest = dict(format=FORMAT, split_policy=SPLIT_POLICY, normalization="NFC; whitespace folded",
                    prompt_overlap_policy="NFC; casefold; punctuation and whitespace folded",
                    generator_sha256=_sha(Path(__file__).read_bytes()), files=files,
                    categories=list(CATEGORIES), license_allowlist=sorted(LICENSE_ALLOWLIST),
                    tokenizer_splits=["train"], training_splits=["train"], selection_splits=["valid"],
                    sealed_splits=["test"], test_prompts=40,
                    provenance="Local synthetic templates and repository-authored seed pairs; no external API teacher",
                    limitations=["Synthetic bounded diagnostic corpus, not natural conversation or a general benchmark",
                                 "Common response labels can repeat; seed groups and normalized prompts are disjoint",
                                 "Closed-fact answers have separately authored supporting train facts; test prompts remain held out",
                                 "Source registry includes sealed seeds and must not be tokenizer/training input"])
    payloads["manifest.json"] = _canonical(manifest) + b"\n"
    root.mkdir(parents=True, exist_ok=True)
    if (root / "manifest.json").exists():
        for split in SPLITS:
            name = split + ".jsonl"
            path = root / name
            if not path.exists() or path.read_bytes() != payloads[name]:
                raise ValueError("refusing to overwrite changed sealed split: " + name)
    for name, raw in payloads.items():
        (root / name).write_bytes(raw)
    return manifest


def load_dataset(root: Path) -> tuple[dict, dict]:
    """Verify snapshot hashes and contracts before returning rows and manifest."""
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT:
        raise ValueError("unknown dataset format")
    policies = dict(split_policy=SPLIT_POLICY, tokenizer_splits=["train"], training_splits=["train"],
                    selection_splits=["valid"], sealed_splits=["test"], test_prompts=40)
    if any(manifest.get(key) != value for key, value in policies.items()):
        raise ValueError("sealed dataset policy mismatch")
    if manifest.get("generator_sha256") != _sha(Path(__file__).read_bytes()):
        raise ValueError("sealed dataset generator hash mismatch")
    expected = {split + ".jsonl" for split in SPLITS} | {"sources.json", "NOTICE.md"}
    if set(manifest.get("files", {})) != expected:
        raise ValueError("missing or unknown manifest file")
    data = {}
    for name in sorted(expected):
        raw = (root / name).read_bytes()
        record = manifest["files"][name]
        if _sha(raw) != record["sha256"] or len(raw) != record["bytes"]:
            raise ValueError("dataset hash or size mismatch: " + name)
        if name.endswith(".jsonl"):
            split = name[:-6]
            data[split] = [json.loads(line) for line in raw.splitlines()]
            if len(data[split]) != record["rows"]:
                raise ValueError("dataset row count mismatch: " + split)
        elif name == "sources.json":
            snapshot_sources = json.loads(raw)
            validate_sources(snapshot_sources)
            if snapshot_sources != _sources():
                raise ValueError("source registry differs from the sealed generator")
    validate_dataset(data)
    return data, manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=SOURCE_ROOT)
    args = parser.parse_args()
    print(json.dumps(write_dataset(args.out), sort_keys=True))
