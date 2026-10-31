#!/usr/bin/env python3
"""Generic 2D swept AABB collision audit for game movement traces.

A segment crossing a box can be blocked even when its destination is outside.
This is a geometric oracle, not evidence of original-game runtime parity.
"""
import argparse
import json
import math
from pathlib import Path


def _pair(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must contain two coordinates")
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in value):
        raise ValueError(f"{name} coordinates must be finite numbers")
    return tuple(float(v) for v in value)


def intersects(start, end, center, half_extents):
    """Return whether a segment touches an axis-aligned 2D rectangle."""
    x0, z0 = _pair(start, "start")
    x1, z1 = _pair(end, "end")
    cx, cz = _pair(center, "center")
    hx, hz = _pair(half_extents, "half_extents")
    if hx <= 0 or hz <= 0:
        raise ValueError("half_extents must be positive")
    enter, leave = 0.0, 1.0
    for origin, delta, lower, upper in (
        (x0, x1-x0, cx-hx, cx+hx),
        (z0, z1-z0, cz-hz, cz+hz),
    ):
        if delta == 0:
            if origin < lower or origin > upper:
                return False
            continue
        a, b = (lower-origin)/delta, (upper-origin)/delta
        if a > b:
            a, b = b, a
        enter, leave = max(enter, a), min(leave, b)
        if enter > leave:
            return False
    return True


def inside(point, center, half_extents):
    x, z = _pair(point, "point")
    cx, cz = _pair(center, "center")
    hx, hz = _pair(half_extents, "half_extents")
    if hx <= 0 or hz <= 0:
        raise ValueError("half_extents must be positive")
    return abs(x-cx) <= hx and abs(z-cz) <= hz


def audit(spec):
    cases = spec.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("cases must be a nonempty array")
    results = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError("case must be an object")
        start = _pair(case.get("start"), "start")
        end = _pair(case.get("end"), "end")
        colliders = case.get("colliders")
        if not isinstance(colliders, list):
            raise ValueError("colliders must be an array")
        swept, endpoint = False, False
        for collider in colliders:
            center = _pair(collider.get("center"), "center")
            extents = _pair(collider.get("half_extents"), "half_extents")
            if min(extents) <= 0:
                raise ValueError("half_extents must be positive")
            start_inside = inside(start, center, extents)
            end_inside = inside(end, center, extents)
            endpoint |= end_inside
            # Permit leaving an overlap caused by spawning inside geometry.
            swept |= (end_inside if start_inside else
                      intersects(start, end, center, extents))
        expected = case.get("expected_blocked")
        if expected is not None and not isinstance(expected, bool):
            raise ValueError("expected_blocked must be a boolean")
        results.append({"name": case.get("name", str(index)),
                        "swept_blocked": swept,
                        "endpoint_blocked": endpoint,
                        "endpoint_missed_collision": swept and not endpoint,
                        "expected_blocked": expected,
                        "pass": expected is None or expected == swept})
    return {"ok": all(x["pass"] for x in results), "cases": results,
            "endpoint_misses": sum(x["endpoint_missed_collision"] for x in results),
            "original_game_parity_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = audit(json.loads(args.spec.read_text(encoding="utf-8")))
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
