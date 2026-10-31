#!/usr/bin/env python3
"""Audit visual and collision coverage of four-way modular wall footprints.

Pure geometry validation: this does not prove parity with a source game.
"""
import argparse
import json
import math
from pathlib import Path


def audit(spec):
    required = ("visual_half_length", "visual_half_thickness",
                "collision_half_length", "collision_half_thickness", "edge_offset")
    dims = {}
    for key in required:
        value = spec.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("missing or nonnumeric dimension: " + key)
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("dimension must be finite and positive: " + key)
        dims[key] = value
    tolerance = spec.get("tolerance", 1e-6)
    if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
            or not math.isfinite(tolerance) or tolerance < 0):
        raise ValueError("invalid tolerance")
    endpoint_gap = max(0.0, dims["visual_half_length"] -
                       dims["collision_half_length"] - tolerance)
    thickness_gap = max(0.0, dims["visual_half_thickness"] -
                        dims["collision_half_thickness"] - tolerance)
    rotations = []
    for turn in range(4):
        along_x = turn % 2 == 0
        sign = -1 if turn in (0, 3) else 1
        center = ((0.0, sign * dims["edge_offset"]) if along_x
                  else (sign * dims["edge_offset"], 0.0))
        rotations.append({"turn": turn, "center_xz": list(center),
                          "tangent_axis": "x" if along_x else "z",
                          "visual_endpoint_covered": endpoint_gap == 0,
                          "visual_thickness_covered": thickness_gap == 0})
    errors = []
    if endpoint_gap:
        errors.append("visual_endpoint_outside_collider")
    if thickness_gap:
        errors.append("visual_surface_outside_collider")
    return {"ok": not errors, "dimensions": dims, "rotations": rotations,
            "endpoint_gap_per_side": endpoint_gap,
            "thickness_gap_per_side": thickness_gap,
            "collision_overhang_normal": dims["collision_half_thickness"] -
                                          dims["visual_half_thickness"],
            "errors": errors, "original_mesh_equivalence_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = audit(json.loads(args.spec.read_text(encoding="utf-8")))
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
