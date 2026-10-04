#!/usr/bin/env python3
"""Report frozen Portuguese quality; never select a checkpoint from test results.

Closed facts use NFC/whitespace-normalized exact answers. The current greetings,
definitions and polite-request instructions are open and need a human ledger
decision bound to SHA-256 of the *unmodified* UTF-8 response. Tool scoring remains
the separate frozen v0.16 exact-answer suite. This command never edits reviews.
"""
import argparse
import base64
import hashlib
import json
import platform
import statistics
import struct
import subprocess
import time
from pathlib import Path

from portuguese_data_v017 import CATEGORIES, ROOT, load_dataset, normalize_text

SCHEMA = "edgeai.portuguese.evaluation.v1"
REVIEW_SCHEMA = "edgeai.portuguese.reviews.v1"
TOOL_ROOT = ROOT / "data/low_resource_v016"


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def score_record(item: dict, response: dict, reviews: dict) -> dict:
    category = item.get("category")
    if category not in (*CATEGORIES, "tool"):
        raise ValueError("unknown evaluation category")
    text = response.get("text")
    malformed = not isinstance(text, str) or not text.strip()
    notes = []
    response_hash = None
    if isinstance(text, str):
        try:
            response_hash = sha256(text.encode("utf-8"))
        except UnicodeEncodeError:
            malformed = True
            notes.append("response text contains invalid Unicode surrogates")
    is_tool = category == "tool"
    mode = "exact" if is_tool or category == "closed_fact" else "human_review"
    expected = item.get("expected_text") if is_tool else item["response"]
    exact = (response_hash is not None and
             (text == expected if is_tool else normalize_text(text) == normalize_text(expected)))
    route_ok = response.get("route") == (item["expected_route"] if is_tool else "neural")
    neural_ok = is_tool or response.get("neural_used") is True
    review = reviews.get(item["id"])
    reviewed = (mode == "human_review" and isinstance(review, dict)
                and review.get("decision") in ("pass", "fail")
                and isinstance(review.get("reviewer"), str) and bool(review["reviewer"].strip())
                and response_hash is not None and review.get("response_sha256") == response_hash)
    approved = reviewed and review["decision"] == "pass"
    if malformed:
        if not notes:
            notes.append("empty or non-string output")
    if not route_ok:
        notes.append("wrong route")
    if not neural_ok:
        notes.append("neural flag missing")
    if mode == "exact" and not exact:
        notes.append("wrong exact answer")
    if mode == "human_review" and not approved:
        notes.append("human rejected response" if reviewed else
                     "human review absent, invalid or bound to a different response hash")
    passed = bool(route_ok and neural_ok and not malformed and
                  (exact if mode == "exact" else approved))
    return dict(id=item["id"], category=category, prompt=item["prompt"],
                expected_text=expected, scoring_mode=mode, passed=passed,
                reviewed=bool(reviewed), review=review if reviewed else None,
                malformed=malformed, empty=isinstance(text, str) and not text.strip(),
                route_ok=route_ok, neural_used=response.get("neural_used"),
                route=response.get("route"), text=text, exact_match=bool(exact),
                response_sha256=response_hash, response=response, notes=notes)


def _counts(group):
    passed, total = sum(record["passed"] for record in group), len(group)
    return dict(passed=passed, total=total, rate=passed / total if total else 0.0)


def summarize(records: list[dict]) -> dict:
    tools = [record for record in records if record["category"] == "tool"]
    neural = [record for record in records if record["category"] != "tool"]
    counts = _counts(neural)
    counts.update(reviewed=sum(record["reviewed"] for record in neural),
                  exact_passed=sum(record["passed"] and record["scoring_mode"] == "exact"
                                   for record in neural),
                  exact_total=sum(record["scoring_mode"] == "exact" for record in neural),
                  human_review_passed=sum(record["passed"] and record["scoring_mode"] == "human_review"
                                          for record in neural),
                  human_review_total=sum(record["scoring_mode"] == "human_review" for record in neural))
    latencies = sorted(record["latency_ms"] for record in records if "latency_ms" in record)
    total = len(records)
    malformed = sum(record["malformed"] for record in records)
    return dict(neural=counts, tool=_counts(tools),
                categories={category: _counts([record for record in neural if record["category"] == category])
                            for category in CATEGORIES},
                malformed=dict(count=malformed, total=total, rate=malformed / total if total else 0.0),
                empty=dict(count=sum(record["empty"] for record in records), total=total),
                wrong_route=dict(count=sum(not record["route_ok"] for record in records), total=total),
                latency_ms_p50=statistics.median(latencies) if latencies else 0.0,
                latency_ms_p95=latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0.0,
                checkpoint_selection_allowed=False, selection_splits=["valid"], evaluation_split="test")


def load_frozen_corpus(corpus: Path, manifest: Path) -> tuple[list[dict], dict]:
    corpus, manifest = Path(corpus).resolve(), Path(manifest).resolve()
    if corpus != manifest.parent / "test.jsonl" or manifest.name != "manifest.json":
        raise ValueError("only the sealed test.jsonl beside its manifest is allowed")
    data, metadata = load_dataset(manifest.parent)
    return data["test"], metadata


def tokenizer_artifact(raw: bytes) -> dict:
    """Hash canonical embedded tokenizer semantics, independent of model weights."""
    if len(raw) < 32 or raw[:8] not in (b"EDGEAI5\0", b"EDGEAI6\0", b"EDGEAI7\0", b"EDGEAI8\0"):
        raise ValueError("unsupported or truncated model tokenizer header")
    version = struct.unpack_from("<I", raw, 8)[0]
    if raw[:8] != ("EDGEAI" + str(version)).encode("ascii") + b"\0":
        raise ValueError("model tokenizer version mismatch")
    if version == 5:
        mode, count, offset = 0, 0, 32
    elif version in (6, 7):
        if len(raw) < 36:
            raise ValueError("truncated tokenizer count")
        mode, count, offset = version - 5, struct.unpack_from("<I", raw, 32)[0], 36
    else:
        if len(raw) < 44:
            raise ValueError("truncated tokenizer count")
        mode, count = struct.unpack_from("<2I", raw, 36)
        offset = 44
    if mode > 2 or count > 4096 - (259 if mode == 2 else 257) or (mode == 0 and count):
        raise ValueError("invalid tokenizer mode or merge count")
    if len(raw) < offset + count * 8:
        raise ValueError("truncated tokenizer merges")
    merges = [list(struct.unpack_from("<2I", raw, offset + index * 8)) for index in range(count)]
    semantics = dict(mode=mode, merges=merges)
    canonical = json.dumps(semantics, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return dict(sha256=sha256(canonical), mode=mode, merge_count=count,
                binding="canonical embedded mode and merges; full model hash also recorded")


def _artifact(path, raw):
    path = Path(path)
    return dict(path=path.as_posix(), sha256=sha256(raw), bytes=len(raw))


def _tool_corpus(raw, manifest_raw):
    metadata = json.loads(manifest_raw.decode("utf-8"))
    if metadata["sha256"] != sha256(raw):
        raise ValueError("frozen tool corpus hash mismatch")
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    tools = [row for row in rows if row["category"] == "tool"]
    if len(rows) != metadata["items"] or len(tools) != metadata["tool_items"] or len(tools) != 20:
        raise ValueError("frozen tool corpus count mismatch")
    return tools


def _run(binary, model, item, reviews):
    command = [str(binary), "--model", str(model), "--threads", "2", "--prompt", item["prompt"]]
    started = time.perf_counter()
    notes = []
    try:
        run = subprocess.run(command, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired as error:
        run = subprocess.CompletedProcess(command, -1, error.stdout or b"", error.stderr or b"")
        notes.append("runtime timeout after 30 seconds")
    latency = round((time.perf_counter() - started) * 1000, 3)
    encoding_valid = True
    try:
        stdout = run.stdout.decode("utf-8")
    except UnicodeDecodeError:
        encoding_valid = False
        stdout = run.stdout.decode("utf-8", errors="replace")
        notes.append("runtime stdout contains invalid UTF-8 bytes; original bytes retained as base64")
    stderr_utf8_valid = True
    try:
        stderr = run.stderr.decode("utf-8")
    except UnicodeDecodeError:
        stderr_utf8_valid = False
        stderr = run.stderr.decode("utf-8", errors="replace")
        notes.append("runtime stderr contains invalid UTF-8 bytes; diagnostic only, original bytes retained as base64")
    response = {}
    try:
        if not encoding_valid:
            raise ValueError("cannot parse invalid UTF-8 output")
        lines = [line for line in stdout.splitlines() if line.strip()]
        if len(lines) != 1:
            raise ValueError("expected one JSON response line")
        response = json.loads(lines[0])
        if not isinstance(response, dict):
            raise ValueError("expected response object")
    except (ValueError, TypeError) as error:
        response = {}
        notes.append("invalid runtime JSON: " + str(error))
    record = score_record(item, response, reviews)
    if run.returncode:
        record["passed"] = False
        record["malformed"] = True
        notes.append("runtime exit code " + str(run.returncode))
    record.update(latency_ms=latency, stdout=stdout, stderr=stderr, exit_code=run.returncode,
                  stderr_utf8_valid=stderr_utf8_valid,
                  stdout_bytes_base64=base64.b64encode(run.stdout).decode("ascii"),
                  stderr_bytes_base64=base64.b64encode(run.stderr).decode("ascii"))
    record["notes"].extend(notes)
    return record


def _compare(result, control):
    if (control.get("schema") != SCHEMA or control.get("evaluation_split") != "test"
            or control.get("checkpoint_selection_allowed") is not False):
        raise ValueError("control must be a frozen report, never a checkpoint-selection result")
    for artifact in ("corpus", "manifest", "tool_corpus", "tool_manifest", "evaluator"):
        if result["artifacts"][artifact]["sha256"] != control["artifacts"][artifact]["sha256"]:
            raise ValueError("control artifact mismatch: " + artifact)
    if result["neural"]["total"] != control["neural"]["total"] or result["tool"]["total"] != control["tool"]["total"]:
        raise ValueError("control denominators differ")
    return dict(purpose="diagnostic comparison only; cannot select checkpoints",
                control_neural=control["neural"], control_tool=control["tool"],
                neural_pass_delta=result["neural"]["passed"] - control["neural"]["passed"],
                tool_pass_delta=result["tool"]["passed"] - control["tool"]["passed"],
                malformed_count_delta=result["malformed"]["count"] - control["malformed"]["count"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binary", "model", "corpus", "manifest", "reviews", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--compare-control", type=Path)
    args = parser.parse_args(argv)
    # Reject aliases to inputs before doing any work or opening the output.
    paths = [args.binary, args.model, args.corpus, args.manifest, args.reviews,
             Path(__file__), TOOL_ROOT / "prompts.jsonl", TOOL_ROOT / "manifest.json"]
    paths.extend(args.manifest.parent / name for name in
                 ("train.jsonl", "valid.jsonl", "test.jsonl", "sources.json", "NOTICE.md"))
    if args.compare_control:
        paths.append(args.compare_control)
    if args.output.resolve() in {path.resolve() for path in paths}:
        raise ValueError("output must not overwrite an evaluation input or review ledger")
    input_paths = dict(binary=args.binary, model=args.model, corpus=args.corpus,
                       manifest=args.manifest, reviews=args.reviews, evaluator=Path(__file__),
                       tool_corpus=TOOL_ROOT / "prompts.jsonl", tool_manifest=TOOL_ROOT / "manifest.json")
    if args.compare_control:
        input_paths["compare_control"] = args.compare_control
    # Parse and hash exactly the same captured bytes. Never hash a later reread.
    snapshots = {name: path.read_bytes() for name, path in input_paths.items()}
    artifacts = {name: _artifact(input_paths[name], raw) for name, raw in snapshots.items()}
    validated_rows, validated_metadata = load_frozen_corpus(args.corpus, args.manifest)
    rows = [json.loads(line) for line in snapshots["corpus"].splitlines() if line.strip()]
    metadata = json.loads(snapshots["manifest"].decode("utf-8"))
    if rows != validated_rows or metadata != validated_metadata:
        raise ValueError("evaluation input changed during validation: corpus or manifest")
    ledger = json.loads(snapshots["reviews"].decode("utf-8"))
    if ledger.get("schema") != REVIEW_SCHEMA or not isinstance(ledger.get("reviews"), dict):
        raise ValueError("invalid review ledger schema")
    reviews = ledger["reviews"]
    if set(reviews) - {row["id"] for row in rows}:
        raise ValueError("review ledger includes IDs outside the frozen neural test")
    artifacts["tokenizer"] = tokenizer_artifact(snapshots["model"])
    tools = _tool_corpus(snapshots["tool_corpus"], snapshots["tool_manifest"])
    def verify_snapshots():
        for name, path in input_paths.items():
            if path.read_bytes() != snapshots[name]:
                raise ValueError("evaluation input changed during run: " + name)
    verify_snapshots()
    records = [_run(args.binary, args.model, item, reviews) for item in rows + tools]
    verify_snapshots()
    result = dict(schema=SCHEMA, **summarize(records), records=records, artifacts=artifacts,
                  historical_v016_neural=dict(passed=0, total=20),
                  runtime=dict(platform=platform.system(), threads=2,
                               latency_scope="one cold native process per prompt; includes startup"),
                  dataset_limitations=metadata["limitations"],
                  scoring_policy=dict(closed_fact="normalized exact", greeting="human_review",
                                      definition="human_review", short_instruction="human_review",
                                      tool="v0.16 exact"))
    if args.compare_control:
        result["comparison"] = _compare(result, json.loads(snapshots["compare_control"].decode("utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # ASCII JSON escapes retain isolated surrogate text without invalid UTF-8.
    args.output.write_bytes((json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                             + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
