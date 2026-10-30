#!/usr/bin/env python3
"""Audit source-extracted 3D world-tile bounds and identify adjacent sectors.

This tool reasons only about mesh bounding boxes. It does not assume that a
matching edge proves collision continuity, matching materials, or scene origin.
It deliberately rejects oversized world objects as neighbor candidates.
"""
import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class Tile:
    mesh: str
    texture: str
    xmin: float
    xmax: float
    zmin: float
    zmax: float
    ymin: float
    ymax: float

    @property
    def width(self):
        return self.xmax - self.xmin

    @property
    def depth(self):
        return self.zmax - self.zmin


def parse_catalog(path):
    records = []
    names = set()
    for number, line in enumerate(Path(path).read_text(encoding="utf8").splitlines(), 1):
        parts = line.split("#", 1)[0].split()
        if not parts:
            continue
        if len(parts) != 8:
            raise ValueError(f"Line {number}: expected mesh texture and six bounds")
        mesh, texture = parts[:2]
        for name, suffix in ((mesh, ".obj"), (texture, ".png")):
            p = PurePosixPath(name)
            if p.is_absolute() or len(p.parts) != 1 or name in (".", "..") or not name.endswith(suffix):
                raise ValueError(f"Line {number}: unsafe asset name {name!r}")
        if mesh in names:
            raise ValueError(f"Line {number}: duplicate mesh {mesh}")
        names.add(mesh)
        try:
            bounds = tuple(float(x) for x in parts[2:])
        except ValueError as exc:
            raise ValueError(f"Line {number}: nonnumeric bounds") from exc
        if not all(math.isfinite(x) for x in bounds):
            raise ValueError(f"Line {number}: nonfinite bounds")
        xmin, xmax, zmin, zmax, ymin, ymax = bounds
        if not (xmin < xmax and zmin < zmax and ymin <= ymax):
            raise ValueError(f"Line {number}: reversed or degenerate bounds")
        records.append(Tile(mesh, texture, *bounds))
    return records


def adjacent_tiles(records, anchor_name, gap_tolerance=1.5, size_tolerance=0.20,
                   min_edge_coverage=0.80):
    if not (0 <= gap_tolerance <= 100 and 0 <= size_tolerance < 1 and
            0 < min_edge_coverage <= 1):
        raise ValueError("Invalid neighbor tolerances")
    matches = [tile for tile in records if tile.mesh == anchor_name]
    if len(matches) != 1:
        raise ValueError("Anchor mesh must occur exactly once")
    anchor = matches[0]
    result = {}
    for direction in ("north", "south", "east", "west"):
        candidates = []
        for tile in records:
            if tile.mesh == anchor.mesh:
                continue
            if direction in ("north", "south"):
                gap = abs((tile.zmin - anchor.zmax) if direction == "north"
                          else (tile.zmax - anchor.zmin))
                overlap = max(0., min(tile.xmax, anchor.xmax) -
                              max(tile.xmin, anchor.xmin))
                edge = anchor.width
            else:
                gap = abs((tile.xmin - anchor.xmax) if direction == "east"
                          else (tile.xmax - anchor.xmin))
                overlap = max(0., min(tile.zmax, anchor.zmax) -
                              max(tile.zmin, anchor.zmin))
                edge = anchor.depth
            if gap > gap_tolerance or overlap < edge * min_edge_coverage:
                continue
            if (abs(tile.width / anchor.width - 1) > size_tolerance or
                    abs(tile.depth / anchor.depth - 1) > size_tolerance):
                continue
            candidates.append((gap, -overlap, tile.mesh, tile))
        if candidates:
            candidates.sort(key=lambda row: row[:3])
            result[direction] = candidates[0][3]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--gap", type=float, default=1.5)
    args = parser.parse_args(argv)
    records = parse_catalog(args.catalog)
    neighbors = adjacent_tiles(records, args.anchor, gap_tolerance=args.gap)
    print(json.dumps({"catalog": str(args.catalog), "records": len(records),
                      "anchor": args.anchor,
                      "neighbors": {k: {"mesh": v.mesh, "texture": v.texture,
                                        "bounds_xz": [v.xmin, v.xmax, v.zmin, v.zmax]}
                                    for k, v in neighbors.items()},
                      "warning": "Bounding-box adjacency is not verified mesh continuity"},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
