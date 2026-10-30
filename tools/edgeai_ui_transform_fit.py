#!/usr/bin/env python3
"""Fit a 2D translation between source UI control centers and real screenshots.

Generic for any source canvas and target viewport. Uses the standard
letterbox scale plus robust median translation, without modifying screenshots.
Only geometric evidence is measured; gameplay parity is never inferred.
"""
import argparse
import json
import math
import statistics
from pathlib import Path


def _point(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must contain two numbers")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError(f"{label} contains invalid coordinates")
    return float(value[0]), float(value[1])


def fit(data, tolerance_px=3.0):
    if not math.isfinite(tolerance_px) or tolerance_px <= 0:
        raise ValueError("tolerance_px must be positive and finite")
    sw, sh = _point(data.get("source_resolution"), "source_resolution")
    tw, th = _point(data.get("target_resolution"), "target_resolution")
    if min(sw, sh, tw, th) <= 0:
        raise ValueError("resolutions must be positive")
    rows = data.get("controls")
    if not isinstance(rows, list) or len(rows) < 3:
        raise ValueError("at least three matched controls are required")
    scale = min(tw / sw, th / sh)
    left = (tw - sw * scale) / 2.0
    top = (th - sh * scale) / 2.0
    names = set()
    measured = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise ValueError("each control requires a name")
        name = row["name"]
        if not name or name in names:
            raise ValueError("control names must be nonempty and unique")
        names.add(name)
        sx, sy = _point(row.get("source_center"), name + ".source_center")
        ox, oy = _point(row.get("observed_center"), name + ".observed_center")
        dx = ox - (left + sx * scale)
        dy = oy - (top + sy * scale)
        measured.append((name, sx, sy, ox, oy, dx, dy))
    dx = statistics.median(row[5] for row in measured)
    dy = statistics.median(row[6] for row in measured)
    details = []
    for name, sx, sy, ox, oy, _, _ in measured:
        px = left + sx * scale + dx
        py = top + sy * scale + dy
        error = math.hypot(px - ox, py - oy)
        details.append({"name": name,
                        "predicted_screen_center": [round(px, 3), round(py, 3)],
                        "observed_screen_center": [ox, oy],
                        "error_px": round(error, 3),
                        "within_tolerance": error <= tolerance_px})
    return {
        "source_resolution": [sw, sh],
        "target_resolution": [tw, th],
        "letterbox_scale": round(scale, 9),
        "translation_screen_pixels": [round(dx, 3), round(dy, 3)],
        "translation_source_units": [round(dx / scale, 3), round(dy / scale, 3)],
        "tolerance_px": tolerance_px,
        "max_residual_px": max(row["error_px"] for row in details),
        "matched_count": sum(row["within_tolerance"] for row in details),
        "total_controls": len(details),
        "alignment_passed": all(row["within_tolerance"] for row in details),
        "controls": details,
        "gameplay_or_original_runtime_parity_proven": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matches", type=Path, help="JSON with canvas sizes and matched control centers")
    parser.add_argument("--tolerance-px", type=float, default=3.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = fit(json.loads(args.matches.read_text(encoding="utf-8")), args.tolerance_px)
    output = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
