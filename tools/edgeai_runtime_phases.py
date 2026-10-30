#!/usr/bin/env python3
"""Audit observed per-frame CPU phase costs from any instrumented game engine.

The named phases are CPU wall-clock intervals. VBO submission and EndDrawing
may block on the graphics driver; they are NOT GPU execution timer queries.
No inferred original-game parity or synthetic benchmark data is produced.
"""
import argparse
import json
import math
import re
from pathlib import Path

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
KEY = r"[a-z][a-z0-9_]*"
DEFAULT_KEYS = ("pose_cpu_ms", "vbo_submit_ms", "end_drawing_ms", "frame_work_ms")


def summarize(log_text, marker="LIOS_PHASE_TIMING", keys=DEFAULT_KEYS):
    if not isinstance(marker, str) or not marker.strip():
        raise ValueError("nonempty marker required")
    keys = tuple(keys)
    if not keys or len(set(keys)) != len(keys) or any(
            not re.fullmatch(KEY, key) for key in keys):
        raise ValueError("invalid metric keys")
    pattern = re.compile(
        re.escape(marker) + r"\s+frames=(\d+)((?:\s+" + KEY +
        r"=" + NUMBER + r")+)")
    windows = []
    for match in pattern.finditer(log_text):
        frames = int(match.group(1))
        if frames <= 0:
            raise ValueError("invalid frame count")
        pairs = re.findall(r"(" + KEY + r")=(" + NUMBER + r")", match.group(2))
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("duplicate phase metric")
        data = {key: float(value) for key, value in pairs}
        if any(key not in data for key in keys):
            raise ValueError("missing required phase metric")
        if any(not math.isfinite(v) or v < 0 for v in data.values()):
            raise ValueError("invalid phase duration")
        if "frame_work_ms" in data:
            included = sum(data.get(k, 0.0) for k in (
                "pose_cpu_ms", "vbo_submit_ms", "end_drawing_ms"))
            if included > data["frame_work_ms"] + 0.025:
                raise ValueError("measured phases exceed frame work time")
        windows.append((frames, data))
    if not windows:
        raise ValueError("no observed phase timing windows")
    all_keys = set(windows[0][1])
    if any(set(data) != all_keys for _, data in windows):
        raise ValueError("inconsistent phase keys between windows")
    total_frames = sum(n for n, _ in windows)
    means = {key: round(sum(n * data[key] for n, data in windows) /
                        total_frames, 4) for key in sorted(all_keys)}
    if "frame_work_ms" in means:
        means["unattributed_cpu_ms"] = round(max(0.0, means["frame_work_ms"] -
            sum(means.get(k, 0.0) for k in (
                "pose_cpu_ms", "vbo_submit_ms", "end_drawing_ms"))), 4)
    components = {k: v for k, v in means.items()
                  if k != "frame_work_ms" and k.endswith("_ms")}
    dominant = max(components, key=components.get) if components else None
    return {
        "observed_windows": len(windows), "observed_frames": total_frames,
        "mean_phase_ms": means, "largest_observed_cpu_component": dominant,
        "measurement": "cpu_wall_clock_not_gpu_timer",
        "original_game_parity_proven": False,
    }


def compare(candidate, baseline):
    keys = set(candidate["mean_phase_ms"]) & set(baseline["mean_phase_ms"])
    result = {}
    for key in sorted(keys):
        old = baseline["mean_phase_ms"][key]
        new = candidate["mean_phase_ms"][key]
        result[key] = (round(100.0 * (new / old - 1.0), 3)
                       if old > 0 else None)
    return {"mean_phase_change_pct": result, "gpu_execution_time_measured": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--marker", default="LIOS_PHASE_TIMING")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    candidate = summarize(args.log.read_text(encoding="utf-8"), args.marker)
    report = {"candidate": candidate}
    if args.baseline:
        baseline = summarize(args.baseline.read_text(encoding="utf-8"), args.marker)
        report["baseline"] = baseline
        report["comparison"] = compare(candidate, baseline)
    output = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
