#!/usr/bin/env python3
"""Generic visibility-vs-CPU-work audit for instrumented real-time render loops.

Input windows must report a frame count, visible-frame count, expensive-stage
call count and measured CPU cost per frame. The cost is CPU wall-clock time,
not a GPU timer. Fully hidden windows must have zero expensive-stage work
within an explicit measurement tolerance. Mixed windows are not attributed
to either mode. This is not proof of original-game equivalence.
"""
import argparse
import json
import math
import re
from pathlib import Path

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
KEY = r"[a-z][a-z0-9_]*"


def audit(log_text, marker="LIOS_PHASE_TIMING", visible_key="visible_frames",
          calls_key="pose_calls", cost_key="pose_cpu_ms", hidden_tolerance_ms=0.05):
    if not marker or not isinstance(marker, str):
        raise ValueError("nonempty marker required")
    if len({visible_key, calls_key, cost_key}) != 3 or any(
            not re.fullmatch(KEY, k) for k in (visible_key, calls_key, cost_key)):
        raise ValueError("invalid metric keys")
    if not math.isfinite(hidden_tolerance_ms) or hidden_tolerance_ms < 0:
        raise ValueError("invalid hidden tolerance")
    pattern = re.compile(re.escape(marker) + r"\s+frames=(\d+)((?:\s+" +
                         KEY + r"=" + NUMBER + r")+)")
    groups = {name: {"windows": 0, "frames": 0, "weighted_cost": 0.0}
              for name in ("visible", "hidden", "mixed")}
    windows = 0
    visible_total = calls_total = frames_total = 0
    for match in pattern.finditer(log_text):
        frames = int(match.group(1))
        pairs = re.findall(r"(" + KEY + r")=(" + NUMBER + r")", match.group(2))
        if frames <= 0 or len({k for k, _ in pairs}) != len(pairs):
            raise ValueError("invalid frame count or duplicate metrics")
        values = dict(pairs)
        if any(k not in values for k in (visible_key, calls_key, cost_key)):
            raise ValueError("missing visibility/work metrics")
        for key in (visible_key, calls_key):
            if not re.fullmatch(r"\d+", values[key]):
                raise ValueError("noninteger frame or call count")
        visible = int(values[visible_key])
        calls = int(values[calls_key])
        cost = float(values[cost_key])
        if visible > frames or calls > visible or not math.isfinite(cost) or cost < 0:
            raise ValueError("work/visibility invariant violated")
        if visible == 0 and cost > hidden_tolerance_ms:
            raise ValueError("expensive stage ran while invisible")
        group = "hidden" if visible == 0 else "visible" if visible == frames else "mixed"
        entry = groups[group]
        entry["windows"] += 1
        entry["frames"] += frames
        entry["weighted_cost"] += frames * cost
        windows += 1
        frames_total += frames
        visible_total += visible
        calls_total += calls
    if not windows:
        raise ValueError("no visibility timing windows")
    return {
        "observed_windows": windows, "observed_frames": frames_total,
        "visible_frames": visible_total, "work_calls": calls_total,
        "groups": {
            name: {"windows": g["windows"], "frames": g["frames"],
                   "mean_cpu_work_ms": (round(g["weighted_cost"] / g["frames"], 4)
                                        if g["frames"] else None)}
            for name, g in groups.items()},
        "hidden_work_tolerance_ms": hidden_tolerance_ms,
        "measurement": "cpu_wall_clock_not_gpu_timer",
        "original_game_parity_proven": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("log", type=Path)
    p.add_argument("--marker", default="LIOS_PHASE_TIMING")
    p.add_argument("--visible-key", default="visible_frames")
    p.add_argument("--calls-key", default="pose_calls")
    p.add_argument("--cost-key", default="pose_cpu_ms")
    p.add_argument("--hidden-tolerance-ms", type=float, default=0.05)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    result = audit(args.log.read_text(encoding="utf-8"), args.marker,
                   args.visible_key, args.calls_key, args.cost_key,
                   args.hidden_tolerance_ms)
    payload = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
