#!/usr/bin/env python3
"""Compare collision-height continuity between two OBJ meshes at seam probes.

Geometry-only differential audit: a small height delta is not evidence that
Unity physics, normals, material transitions, or navigation are equivalent.
"""
import argparse
import json
import math
from pathlib import Path

from edgeai_obj_surface import Surface


def audit_seam(inner, outer, probes, max_step=0.55):
    if not math.isfinite(max_step) or max_step < 0:
        raise ValueError("Invalid maximum step")
    if not probes:
        raise ValueError("At least one seam probe is required")
    rows = []
    for ix, iz, ox, oz in probes:
        if not all(math.isfinite(v) for v in (ix, iz, ox, oz)):
            raise ValueError("Nonfinite seam probe")
        ih, ic = inner.height_at(ix, iz)
        oh, oc = outer.height_at(ox, oz)
        delta = oh - ih if ih is not None and oh is not None else None
        rows.append({"inner": [ix, iz], "outer": [ox, oz],
                     "inner_height": ih, "outer_height": oh,
                     "inner_hits": ic, "outer_hits": oc,
                     "delta": delta,
                     "covered": delta is not None,
                     "within_step": delta is not None and abs(delta) <= max_step})
    return {"max_step": max_step, "probes": rows,
            "covered_count": sum(row["covered"] for row in rows),
            "pass": all(row["within_step"] for row in rows)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inner", type=Path)
    parser.add_argument("outer", type=Path)
    parser.add_argument("--axis", choices=("unity-z-up", "y-up"), default="unity-z-up")
    parser.add_argument("--probe", type=float, nargs=4, action="append", required=True,
                        metavar=("INNER_X", "INNER_Z", "OUTER_X", "OUTER_Z"))
    parser.add_argument("--max-step", type=float, default=0.55)
    args = parser.parse_args(argv)
    inner = Surface.from_obj(args.inner, axis=args.axis)
    outer = Surface.from_obj(args.outer, axis=args.axis)
    result = audit_seam(inner, outer, args.probe, max_step=args.max_step)
    result.update({"inner_source": str(args.inner), "outer_source": str(args.outer),
                   "axis": args.axis,
                   "warning": "Geometry heights only; not original physics parity"})
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
