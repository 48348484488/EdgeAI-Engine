#!/usr/bin/env python3
"""Conservative, dependency-free OBJ surface-height audit for 3D game assets.

Reads geometry, not game logic. UnityPy-exported Z-up meshes can be converted to
Y-up with (x, y, z) -> (x, z, -y). A vertical ray query reports the highest
triangle intersection; it does not establish a walkable/navmesh surface.
"""
import argparse
import json
import math
from pathlib import Path


class Surface:
    def __init__(self, vertices, triangles, skipped=0):
        self.vertices = vertices
        self.triangles = triangles
        self.skipped = skipped

    @classmethod
    def from_obj(cls, source, axis="unity-z-up", max_vertices=2_000_000,
                 max_triangles=4_000_000):
        if axis not in ("unity-z-up", "y-up"):
            raise ValueError("Unsupported axis conversion")
        vertices, triangles = [], []
        skipped = 0
        with open(source, "r", encoding="utf-8", errors="strict") as stream:
            for line_number, line in enumerate(stream, 1):
                fields = line.split()
                if not fields or fields[0].startswith("#"):
                    continue
                if fields[0] == "v":
                    if len(fields) < 4:
                        raise ValueError(f"Malformed vertex at line {line_number}")
                    try:
                        x, y, z = (float(v) for v in fields[1:4])
                    except ValueError as exc:
                        raise ValueError(f"Invalid vertex at line {line_number}") from exc
                    if not all(math.isfinite(v) for v in (x, y, z)):
                        raise ValueError(f"Nonfinite vertex at line {line_number}")
                    vertices.append((x, z, -y) if axis == "unity-z-up" else (x, y, z))
                    if len(vertices) > max_vertices:
                        raise ValueError("Vertex limit exceeded")
                elif fields[0] == "f":
                    if len(fields) < 4:
                        skipped += 1
                        continue
                    indices = []
                    for token in fields[1:]:
                        try:
                            raw = int(token.split("/")[0])
                        except ValueError as exc:
                            raise ValueError(f"Invalid face at line {line_number}") from exc
                        if raw == 0:
                            raise ValueError(f"OBJ index zero at line {line_number}")
                        index = raw - 1 if raw > 0 else len(vertices) + raw
                        if index < 0 or index >= len(vertices):
                            raise ValueError(f"Out-of-range face at line {line_number}")
                        indices.append(index)
                    for j in range(1, len(indices) - 1):
                        triangles.append((indices[0], indices[j], indices[j + 1]))
                        if len(triangles) > max_triangles:
                            raise ValueError("Triangle limit exceeded")
        return cls(vertices, triangles, skipped)

    def bounds(self):
        if not self.vertices:
            return None
        return {name: [min(v[i] for v in self.vertices),
                       max(v[i] for v in self.vertices)]
                for i, name in enumerate(("x", "y", "z"))}

    def height_at(self, x, z, tolerance=1e-7):
        """Return (top height, number of intersections); None means no coverage."""
        if not all(math.isfinite(v) for v in (x, z)):
            raise ValueError("Query must be finite")
        top, hits = None, 0
        for ia, ib, ic in self.triangles:
            a, b, c = (self.vertices[i] for i in (ia, ib, ic))
            den = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
            if abs(den) < 1e-12:
                continue
            u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / den
            v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / den
            w = 1.0 - u - v
            if min(u, v, w) < -tolerance:
                continue
            y = u * a[1] + v * b[1] + w * c[1]
            hits += 1
            if top is None or y > top:
                top = y
        return top, hits


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("obj", type=Path)
    parser.add_argument("--axis", choices=("unity-z-up", "y-up"), default="unity-z-up")
    parser.add_argument("--x", type=float, default=0.0)
    parser.add_argument("--z", type=float, default=0.0)
    args = parser.parse_args(argv)
    mesh = Surface.from_obj(args.obj, args.axis)
    height, hits = mesh.height_at(args.x, args.z)
    print(json.dumps({"source": str(args.obj), "axis": args.axis,
                      "vertices": len(mesh.vertices), "triangles": len(mesh.triangles),
                      "skipped_faces": mesh.skipped, "bounds": mesh.bounds(),
                      "query": {"x": args.x, "z": args.z,
                                "top_height": height, "intersections": hits}},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
