#!/usr/bin/env python3
"""Compare runtime terrain seam events with independently measured source geometry.

No game-specific coordinates are embedded. Input is a log and a JSON reference
with seams[].direction, inner_height, outer_height. This is a diagnostic of
sampled collision heights, NOT proof of traversability or engine parity.
"""
import argparse
import json
import math
import re
from pathlib import Path

EVENT = re.compile(
    r"(?<!\w){marker}\s+(?P<direction>[A-Za-z][\w-]*)\s+"
    r"inner=(?P<inner>\S+)\s+outer=(?P<outer>\S+)\s+"
    r"height_in=(?P<hin>\S+)\s+height_out=(?P<hout>\S+)"
)


def audit_runtime(log_text, reference, marker="LIOS_TERRAIN_SEAM_PROBE",
                  max_step=0.55, tolerance=0.01):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", marker):
        raise ValueError("Invalid event marker")
    if not all(math.isfinite(v) and v >= 0 for v in (max_step, tolerance)):
        raise ValueError("Invalid step or tolerance")
    seams = reference.get("seams")
    if not isinstance(seams, list) or not seams:
        raise ValueError("Reference requires nonempty seams")
    expected = {}
    for seam in seams:
        direction = seam["direction"]
        if direction in expected:
            raise ValueError("Duplicate reference direction")
        values = (float(seam["inner_height"]), float(seam["outer_height"]))
        if not all(math.isfinite(v) for v in values):
            raise ValueError("Nonfinite reference height")
        expected[direction] = values
    pattern = re.compile(EVENT.pattern.format(marker=re.escape(marker)))
    seen = {}
    errors = []
    for match in pattern.finditer(log_text):
        direction = match.group("direction")
        if direction in seen:
            errors.append("duplicate runtime direction: " + direction)
            continue
        try:
            hin, hout = float(match.group("hin")), float(match.group("hout"))
            covered = match.group("inner") == "1" and match.group("outer") == "1"
        except ValueError:
            errors.append("invalid runtime height: " + direction)
            continue
        if not all(math.isfinite(v) for v in (hin, hout)):
            errors.append("nonfinite runtime height: " + direction)
            continue
        seen[direction] = (hin, hout, covered)
    rows = []
    for direction, (ih, oh) in expected.items():
        if direction not in seen:
            errors.append("missing runtime direction: " + direction)
            continue
        hin, hout, covered = seen[direction]
        delta = hout - hin
        within_tolerance = abs(hin - ih) <= tolerance and abs(hout - oh) <= tolerance
        within_step = abs(delta) <= max_step
        if not covered:
            errors.append("missing runtime collision coverage: " + direction)
        if not within_tolerance:
            errors.append("source/runtime height mismatch: " + direction)
        if not within_step:
            errors.append("excessive runtime step: " + direction)
        rows.append({"direction": direction, "height_in": hin, "height_out": hout,
                     "delta": delta, "covered": covered,
                     "source_height_in": ih, "source_height_out": oh,
                     "within_tolerance": within_tolerance, "within_step": within_step})
    for direction in seen.keys() - expected.keys():
        errors.append("unexpected runtime direction: " + direction)
    return {"pass": not errors, "errors": sorted(errors), "probes": rows,
            "max_step": max_step, "tolerance": tolerance,
            "note": "Sampled geometry/collision parity only; not traversal or original physics parity"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("log", type=Path)
    p.add_argument("reference", type=Path)
    p.add_argument("--marker", default="LIOS_TERRAIN_SEAM_PROBE")
    p.add_argument("--max-step", type=float, default=0.55)
    p.add_argument("--tolerance", type=float, default=0.01)
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    report = audit_runtime(args.log.read_text(encoding="utf8", errors="replace"),
                           json.loads(args.reference.read_text(encoding="utf8")),
                           marker=args.marker, max_step=args.max_step,
                           tolerance=args.tolerance)
    serialized = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf8")
    print(serialized)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
