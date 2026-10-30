#!/usr/bin/env python3
"""Validate and compare measured frame pacing from instrumented game logs.

Uses observed timing windows only. No synthetic FPS estimates or claims of
visual/functional parity. Reusable for any engine emitting the marker below.
"""
import argparse
import json
import math
import re
from pathlib import Path

MARKER = re.compile(
    r"LIOS_FRAME_TIMING\s+frames=(\d+)\s+mean_ms=([0-9.eE+-]+)"
    r"\s+p95_ms=([0-9.eE+-]+)\s+max_ms=([0-9.eE+-]+)"
    r"\s+slow_33ms=(\d+)\s+mean_fps=([0-9.eE+-]+)"
)


def summarize(log_text):
    windows = []
    for match in MARKER.finditer(log_text):
        frames = int(match[1])
        mean, p95, maximum = (float(match[i]) for i in (2, 3, 4))
        slow = int(match[5])
        fps = float(match[6])
        if not (frames > 0 and 0 <= slow <= frames and
                all(math.isfinite(v) for v in (mean, p95, maximum, fps)) and
                0 < mean <= p95 <= maximum and fps > 0):
            raise ValueError("invalid frame timing window")
        if abs(fps - 1000.0 / mean) > max(0.5, fps * 0.01):
            raise ValueError("reported FPS disagrees with frame duration")
        windows.append(dict(frames=frames, mean_ms=mean, p95_ms=p95,
                            max_ms=maximum, slow_33ms=slow, mean_fps=fps))
    if not windows:
        raise ValueError("no observed LIOS_FRAME_TIMING windows in log")
    count = sum(w["frames"] for w in windows)
    total_ms = sum(w["frames"] * w["mean_ms"] for w in windows)
    return dict(observed_windows=len(windows), observed_frames=count,
                mean_ms=round(total_ms / count, 3),
                mean_fps=round(1000.0 * count / total_ms, 3),
                worst_window_p95_ms=max(w["p95_ms"] for w in windows),
                max_ms=max(w["max_ms"] for w in windows),
                slow_33ms=sum(w["slow_33ms"] for w in windows),
                slow_frame_fraction=round(sum(w["slow_33ms"] for w in windows) / count, 5),
                measurement="runtime_frame_pacing_not_gpu_only",
                original_game_parity_proven=False)


def compare(candidate, baseline, max_regression_pct=5.0):
    if not math.isfinite(max_regression_pct) or max_regression_pct < 0:
        raise ValueError("invalid regression threshold")
    change = 100.0 * (candidate["mean_ms"] / baseline["mean_ms"] - 1)
    return dict(mean_frame_time_change_pct=round(change, 3),
                regression_threshold_pct=max_regression_pct,
                regression_detected=change > max_regression_pct,
                original_game_parity_proven=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--max-regression-pct", type=float, default=5.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = dict(candidate=summarize(args.log.read_text(encoding="utf-8")))
    if args.baseline:
        base = summarize(args.baseline.read_text(encoding="utf-8"))
        result["baseline"] = base
        result["comparison"] = compare(result["candidate"], base, args.max_regression_pct)
    output = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")
    if result.get("comparison", {}).get("regression_detected"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
