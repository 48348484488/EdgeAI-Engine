#!/usr/bin/env python3
"""Audit actual joystick/avatar movement against an independent swept-AABB oracle.

Input JSON has records with frame, x/z, target_x/target_z, blocked and
terrain flags, plus colliders with center and half_extents. All coordinates
are world-space ground-plane meters. This is engine-agnostic telemetry,
not proof of equivalence to a proprietary game.
"""
import argparse
import json
import math
from pathlib import Path
from edgeai_swept_collision_audit import audit as swept_audit


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + " must be finite")
    return float(value)


def flag(value, name):
    if type(value) is bool:
        return value
    if type(value) is int and value in (0, 1):
        return bool(value)
    raise ValueError(name + " must be boolean or 0/1")


def near_face(point, collider, tolerance):
    x, z = point
    cx, cz = collider["center"]
    hx, hz = collider["half_extents"]
    return (abs(abs(x-cx)-hx) <= tolerance and abs(z-cz) <= hz+tolerance or
            abs(abs(z-cz)-hz) <= tolerance and abs(x-cx) <= hx+tolerance)


def outside_clearance(point, collider):
    """Euclidean distance from a ground-plane point to an AABB (zero inside)."""
    x, z = point
    cx, cz = collider["center"]
    hx, hz = collider["half_extents"]
    return math.hypot(max(abs(x-cx)-hx, 0.0), max(abs(z-cz)-hz, 0.0))


def audit_trace(spec):
    mode = spec.get("mode", "contact")
    if mode not in ("contact", "retreat"):
        raise ValueError("mode must be contact or retreat")
    records = spec.get("records")
    colliders = spec.get("colliders")
    if not isinstance(records, list) or not records:
        raise ValueError("records must be a nonempty list")
    if not isinstance(colliders, list) or not colliders:
        raise ValueError("colliders must be a nonempty list")
    tolerance = finite(spec.get("boundary_tolerance", .002), "boundary_tolerance")
    if tolerance < 0:
        raise ValueError("boundary_tolerance must be nonnegative")
    # Validate geometry once using the existing generic oracle.
    swept_audit({"cases": [{"start": [0, 0], "end": [0, 0],
                            "colliders": colliders}]})
    normalized = []
    for row in records:
        if not isinstance(row, dict) or type(row.get("frame")) is not int or row["frame"] < 0:
            raise ValueError("frame must be a nonnegative integer")
        normalized.append({
            "frame": row["frame"],
            "start": [finite(row.get("x"), "x"), finite(row.get("z"), "z")],
            "target": [finite(row.get("target_x"), "target_x"),
                       finite(row.get("target_z"), "target_z")],
            "blocked": flag(row.get("blocked"), "blocked"),
            "terrain": flag(row.get("terrain"), "terrain"),
        })
    if any(b["frame"] <= a["frame"] for a, b in zip(normalized, normalized[1:])):
        raise ValueError("frames must increase strictly")
    checked, mismatches, boundary_ambiguous = 0, [], 0
    free, blocked = [], []
    for row in normalized:
        if row["terrain"]:
            continue
        expected = swept_audit({"cases": [{
            "start": row["start"], "end": row["target"],
            "colliders": colliders} ]})["cases"][0]["swept_blocked"]
        ambiguous = any(near_face(row["start"], c, tolerance) or
                        near_face(row["target"], c, tolerance) for c in colliders)
        if expected != row["blocked"]:
            if ambiguous:
                boundary_ambiguous += 1
            else:
                mismatches.append({"frame": row["frame"], "expected": expected,
                                   "observed": row["blocked"]})
        else:
            checked += 1
        (blocked if row["blocked"] else free).append(row)
    travel = math.dist(normalized[0]["start"], normalized[-1]["start"])
    drift = max((math.dist(blocked[0]["start"], r["start"]) for r in blocked),
                default=0.0) if blocked else 0.0
    min_samples = int(spec.get("min_samples", 5))
    min_free = int(spec.get("min_free", 2))
    min_blocked = int(spec.get("min_blocked", 2))
    min_travel = finite(spec.get("min_travel", .15), "min_travel")
    max_drift = finite(spec.get("max_contact_drift", .12), "max_contact_drift")
    if min_samples < 1 or min_free < 0 or min_blocked < 0 or min_travel < 0 or max_drift < 0:
        raise ValueError("invalid audit thresholds")
    checks = {
        "enough_samples": len(normalized) >= min_samples,
        "free_movement": len(free) >= min_free and travel >= min_travel,
        "independent_oracle": not mismatches and checked >= min_free,
        "blocked_input_nonzero": all(math.dist(r["start"], r["target"]) > .0001
                                      for r in blocked),
    }
    clearance_gain = None
    if mode == "contact":
        checks["wall_contact"] = len(blocked) >= min_blocked and drift <= max_drift
        checks["independent_oracle"] &= checked >= min_free+min_blocked
    else:
        # A retreat must create measurable clearance from the nearest collider,
        # not merely move sideways along a blocked surface.
        start_clearance = min(outside_clearance(normalized[0]["start"], c)
                              for c in colliders)
        end_clearance = min(outside_clearance(normalized[-1]["start"], c)
                            for c in colliders)
        clearance_gain = end_clearance - start_clearance
        min_gain = finite(spec.get("min_clearance_gain", .15), "min_clearance_gain")
        max_blocked = spec.get("max_retreat_blocked", 1)
        if min_gain < 0 or type(max_blocked) is not int or max_blocked < 0:
            raise ValueError("invalid retreat thresholds")
        checks["retreat_clearance"] = clearance_gain >= min_gain
        checks["retreat_unblocked"] = len(blocked) <= max_blocked
    return {
        "ok": all(checks.values()), "checks": checks,
        "mode": mode, "clearance_gain_m": (
            round(clearance_gain, 5) if clearance_gain is not None else None),
        "samples": len(normalized), "free": len(free), "blocked": len(blocked),
        "travel_m": round(travel, 5), "contact_drift_m": round(drift, 5),
        "oracle_matches": checked, "oracle_mismatches": mismatches,
        "boundary_ambiguous": boundary_ambiguous,
        "original_game_parity_verified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = audit_trace(json.loads(args.spec.read_text(encoding="utf-8")))
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
