#!/usr/bin/env python3
"""Compare source OBJ seam heights with actual runtime collision log samples.

Supports one midpoint or several explicitly identified offsets per seam.
This tests collision sampling, NOT continuous player traversal or Unity physics.
"""
import argparse
import json
import math
import re
from pathlib import Path

EVENT = re.compile(
    r"(?<!\w){marker}\s+(?P<direction>[A-Za-z][\w-]*)\s+"
    r"(?:offset=(?P<offset>\S+)\s+)?"
    r"inner=(?P<inner>\S+)\s+outer=(?P<outer>\S+)\s+"
    r"height_in=(?P<hin>\S+)\s+height_out=(?P<hout>\S+)"
)


def _finite_number(value, label):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Invalid " + label)
    if not math.isfinite(number):
        raise ValueError("Nonfinite " + label)
    return number


def _name(key):
    direction, offset = key
    return direction if offset == 0 else f"{direction}@{offset:g}"


def audit_runtime(log_text, reference, marker="LIOS_TERRAIN_SEAM_PROBE",
                  max_step=0.55, tolerance=0.01):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", marker):
        raise ValueError("Invalid event marker")
    max_step = _finite_number(max_step, "step")
    tolerance = _finite_number(tolerance, "tolerance")
    if max_step < 0 or tolerance < 0:
        raise ValueError("Invalid step or tolerance")
    seams = reference.get("seams")
    if not isinstance(seams, list) or not seams:
        raise ValueError("Reference requires nonempty seams")
    expected = {}
    for seam in seams:
        direction = seam["direction"]
        if not isinstance(direction, str) or not re.fullmatch(r"[A-Za-z][\w-]*", direction):
            raise ValueError("Invalid reference direction")
        offset = _finite_number(seam.get("offset", 0), "reference offset")
        key = (direction, offset)
        if key in expected:
            raise ValueError("Duplicate reference probe: " + _name(key))
        values = (_finite_number(seam["inner_height"], "reference inner height"),
                  _finite_number(seam["outer_height"], "reference outer height"))
        expected[key] = values
    pattern = re.compile(EVENT.pattern.format(marker=re.escape(marker)))
    seen = {}
    errors = []
    for line in log_text.splitlines():
        if marker not in line:
            continue
        match = pattern.search(line)
        if match is None:
            errors.append("malformed runtime event")
            continue
        direction = match.group("direction")
        try:
            offset = _finite_number(match.group("offset") or 0, "runtime offset")
            hin = _finite_number(match.group("hin"), "runtime inner height")
            hout = _finite_number(match.group("hout"), "runtime outer height")
        except ValueError:
            errors.append("invalid runtime height or offset: " + direction)
            continue
        key = (direction, offset)
        if key in seen:
            errors.append("duplicate runtime direction: " + _name(key))
            continue
        covered = match.group("inner") == "1" and match.group("outer") == "1"
        seen[key] = (hin, hout, covered)
    rows = []
    for key, (ih, oh) in expected.items():
        if key not in seen:
            errors.append("missing runtime direction: " + _name(key))
            continue
        hin, hout, covered = seen[key]
        delta = hout - hin
        within_tolerance = abs(hin - ih) <= tolerance and abs(hout - oh) <= tolerance
        within_step = abs(delta) <= max_step
        name = _name(key)
        if not covered:
            errors.append("missing runtime collision coverage: " + name)
        if not within_tolerance:
            errors.append("source/runtime height mismatch: " + name)
        if not within_step:
            errors.append("excessive runtime step: " + name)
        rows.append({"direction": key[0], "offset": key[1],
                     "height_in": hin, "height_out": hout,
                     "delta": delta, "covered": covered,
                     "source_height_in": ih, "source_height_out": oh,
                     "within_tolerance": within_tolerance, "within_step": within_step})
    for key in seen.keys() - expected.keys():
        errors.append("unexpected runtime direction: " + _name(key))
    return {"pass": not errors, "errors": sorted(errors), "probes": rows,
            "max_step": max_step, "tolerance": tolerance,
            "note": "Sampled collision parity only; not traversal or original physics parity"}


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
