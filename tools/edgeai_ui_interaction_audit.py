#!/usr/bin/env python3
"""Audit source-UI geometry against observed screenshot centers and real touch traces.

The fitted transform is an empirical screen mapping, not a recovered game
engine CanvasScaler. Touch events must be supplied from actual runtime logs;
this tool never invents actions or claims parity with an original game.
"""
import argparse
import json
import math
import sys
from pathlib import Path

# Also work when loaded by importlib from tests outside the tools directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from edgeai_ui_transform_fit import fit


def _point(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must have two coordinates")
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError(f"{name} must contain finite numbers")
    return [float(x) for x in value]


def audit(data, tolerance_px=3.0):
    alignment = fit(data, tolerance_px=tolerance_px)
    rows = {row["name"]: row for row in data["controls"]}
    source_w, source_h = alignment["source_resolution"]
    scale = alignment["letterbox_scale"]
    target_w, target_h = alignment["target_resolution"]
    left = (target_w - source_w * scale) / 2 + alignment["translation_screen_pixels"][0]
    top = (target_h - source_h * scale) / 2 + alignment["translation_screen_pixels"][1]
    bounds = {}
    for name, row in rows.items():
        rect = row.get("source_bounds")
        if rect is None:
            continue
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            raise ValueError(f"{name}.source_bounds must contain four coordinates")
        x1, y1 = _point(rect[:2], name + ".source_bounds")
        x2, y2 = _point(rect[2:], name + ".source_bounds")
        if x1 >= x2 or y1 >= y2:
            raise ValueError(f"{name}.source_bounds must have positive area")
        bounds[name] = [left + x1 * scale, top + y1 * scale,
                        left + x2 * scale, top + y2 * scale]
    trials = data.get("touch_trials")
    if not isinstance(trials, list) or not trials:
        raise ValueError("at least one observed touch trial is required")
    result = []
    for i, trial in enumerate(trials):
        if not isinstance(trial, dict):
            raise ValueError("touch trials must be objects")
        name = trial.get("control")
        if name not in bounds:
            raise ValueError(f"touch trial {i} has unknown control or missing source_bounds")
        event = trial.get("action_observed")
        if type(event) is not bool:
            raise ValueError("action_observed must be an explicit boolean from runtime evidence")
        px, py = _point(trial.get("screen_point"), "screen_point")
        x1, y1, x2, y2 = bounds[name]
        inside = x1 <= px <= x2 and y1 <= py <= y2
        if not alignment["alignment_passed"]:
            verdict = "geometry_unreliable"
        elif inside and event:
            verdict = "observed_inside_activation"
        elif inside and not event:
            verdict = "inside_but_no_activation"
        elif not inside and event:
            verdict = "outside_but_activated"
        else:
            verdict = "outside_no_activation"
        result.append({"control": name, "screen_point": [px, py],
                       "predicted_screen_bounds": [round(v, 3) for v in bounds[name]],
                       "inside_fitted_bounds": inside,
                       "action_observed": event, "verdict": verdict})
    contradictions = {"inside_but_no_activation", "outside_but_activated"}
    return {"alignment": alignment,
            "touch_trials": result,
            "observed_activation_count": sum(r["action_observed"] for r in result),
            "geometry_runtime_disagreements": sum(r["verdict"] in contradictions for r in result),
            "original_game_parity_proven": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--tolerance-px", type=float, default=3.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = audit(json.loads(args.evidence.read_text(encoding="utf-8")), args.tolerance_px)
    output = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
