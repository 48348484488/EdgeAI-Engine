#!/usr/bin/env python3
"""Run the focused CLI under the OS resource meter and enforce hard budgets."""
import argparse
import json
import pathlib
import re
import subprocess
import tempfile


LIMITS = {
    "peak_rss_bytes": 64 * 1024 * 1024,
    "startup_ms": 2000,
    "model_file_bytes": 16 * 1024 * 1024,
    "threads": 2,
}


def parse_peak_rss_bytes(text: str) -> int:
    match = re.search(r"Maximum resident set size \(kbytes\):\s*([0-9]+)", text)
    if not match:
        raise ValueError("authoritative peak RSS is missing")
    return int(match.group(1)) * 1024


def enforce(metrics: dict) -> None:
    for key, limit in LIMITS.items():
        if key not in metrics:
            raise ValueError(f"required metric is missing: {key}")
        if int(metrics[key]) > limit:
            raise ValueError(f"{key}={metrics[key]} exceeds {limit}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt", default="Explain entropy briefly.")
    parser.add_argument("--workload")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        internal = pathlib.Path(temporary) / "internal.json"
        command = ["/usr/bin/time", "-v", args.binary, "--model", args.model,
                   "--threads", str(args.threads), "--metrics-json", str(internal)]
        command += ["--workload", args.workload] if args.workload else ["--prompt", args.prompt]
        run = subprocess.run(command, text=True, capture_output=True, timeout=30)
        if run.returncode:
            raise RuntimeError(run.stderr or run.stdout)
        metrics = json.loads(internal.read_text(encoding="utf-8"))
        metrics["peak_rss_bytes"] = parse_peak_rss_bytes(run.stderr)
        enforce(metrics)
        output = pathlib.Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
