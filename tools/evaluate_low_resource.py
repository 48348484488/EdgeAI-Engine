#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import statistics
import subprocess
import time


def validate_corpus(rows):
    ids = [row.get("id") for row in rows]
    if any(not value for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("corpus IDs must be present and unique")
    for row in rows:
        if row.get("category") not in {"tool", "neural"}:
            raise ValueError(f"invalid category for {row['id']}")


def score(item, response):
    text = response.get("text")
    malformed = not isinstance(text, str) or not text.strip()
    notes = []
    route_ok = response.get("route") == item.get("expected_route")
    if not route_ok:
        notes.append("wrong route")
    if item["category"] == "tool":
        exact = text == item.get("expected_text")
        if not exact:
            notes.append("wrong exact answer")
        return route_ok and exact and not malformed, malformed, notes
    neural_flag = response.get("neural_used") is True
    if not neural_flag:
        notes.append("neural flag missing")
    if item.get("rubric") == "human_review":
        approved_hash = item.get("expected_response_sha256")
        actual_hash = hashlib.sha256(text.encode("utf-8")).hexdigest() if isinstance(text, str) else ""
        if not item.get("manual_pass", False) or approved_hash != actual_hash:
            notes.append("human review is absent or bound to a different response hash")
            return False, malformed, notes
    return route_ok and neural_flag and not malformed, malformed, notes


def summarize(records):
    tools = [r for r in records if r["category"] == "tool"]
    neural = [r for r in records if r["category"] == "neural"]
    latencies = sorted(r["latency_ms"] for r in records)
    def rate(group):
        return sum(bool(r["passed"]) for r in group) / len(group) if group else 0.0
    return {
        "tool_accuracy": rate(tools),
        "neural_rubric_pass_rate": rate(neural),
        "malformed_rate": sum(bool(r["malformed"]) for r in records) / len(records) if records else 0.0,
        "latency_ms_p50": statistics.median(latencies) if latencies else 0.0,
        "latency_ms_p95": latencies[min(len(latencies)-1, int(len(latencies)*0.95))] if latencies else 0.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--manifest")
    parser.add_argument("--output", required=True)
    parser.add_argument("--baseline")
    args = parser.parse_args()
    corpus_path = pathlib.Path(args.corpus)
    raw = corpus_path.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    validate_corpus(rows)
    if args.manifest:
        manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
        if manifest["sha256"] != hashlib.sha256(raw).hexdigest():
            raise ValueError("corpus hash mismatch")
    records = []
    for item in rows:
        started = time.perf_counter()
        run = subprocess.run([args.binary, "--model", args.model, "--prompt", item["prompt"]],
                             capture_output=True, text=True, timeout=10, check=True)
        response = json.loads(run.stdout.strip().splitlines()[-1])
        passed, malformed, notes = score(item, response)
        records.append({"id": item["id"], "category": item["category"], "passed": passed,
                        "malformed": malformed, "latency_ms": round((time.perf_counter()-started)*1000, 3),
                        "route": response.get("route"), "text": response.get("text"), "notes": notes})
    result = {"schema": "edgeai.low-resource.evaluation.v1", **summarize(records), "records": records}
    if args.baseline:
        baseline = json.loads(pathlib.Path(args.baseline).read_text(encoding="utf-8"))
        if result["neural_rubric_pass_rate"] < baseline["neural_rubric_pass_rate"]:
            raise ValueError("neural rubric pass rate regressed")
        if result["malformed_rate"] > baseline["malformed_rate"]:
            raise ValueError("malformed response rate regressed")
    output = pathlib.Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
