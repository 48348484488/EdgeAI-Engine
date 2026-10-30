"""OBJ height sampling tests with known geometry, independent of Unity runtime."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "edgeai_obj_surface.py"
spec = importlib.util.spec_from_file_location("edgeai_obj_surface", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SurfaceTests(unittest.TestCase):
    def load(self, data, axis="y-up"):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mesh.obj"
            path.write_text(data, encoding="utf8")
            return mod.Surface.from_obj(path, axis)

    def test_triangle_barycentric_height(self):
        mesh = self.load("v 0 2 0\nv 2 4 0\nv 0 2 2\nf 1 2 3\n")
        self.assertEqual(mesh.height_at(0.5, 0.5), (2.5, 1))
        self.assertEqual(mesh.height_at(4, 4), (None, 0))

    def test_unity_z_up_and_negative_quad_indices(self):
        mesh = self.load("v 0 0 5\nv 2 0 5\nv 2 -2 7\nv 0 -2 7\nf -4/-1 -3/-1 -2/-1 -1/-1\n", "unity-z-up")
        self.assertEqual(len(mesh.triangles), 2)
        self.assertEqual(mesh.height_at(1, 1), (6.0, 2))
        self.assertEqual(mesh.bounds(), {"x": [0., 2.], "y": [5., 7.], "z": [0., 2.]})

    def test_highest_intersection_not_walkability(self):
        mesh = self.load("v 0 0 0\nv 2 0 0\nv 0 0 2\nv 0 5 0\nv 2 5 0\nv 0 5 2\nf 1 2 3\nf 4 5 6\n")
        self.assertEqual(mesh.height_at(0.5, 0.5), (5., 2))

    def test_invalid_vertices_and_faces_fail_closed(self):
        for source in ("v 0 nan 0\n", "v 0 0 0\nf 0 1 1\n", "v 0 0 0\nf 1 2 3\n"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.load(source)
        mesh = self.load("v 0 0 0\nv 1 0 0\nv 0 0 1\nf 1 2 3\n")
        with self.assertRaises(ValueError):
            mesh.height_at(float("nan"), 0)

    def test_degenerate_face_does_not_create_ground(self):
        mesh = self.load("v 0 1 0\nv 1 1 0\nv 2 1 0\nf 1 2 3\n")
        self.assertEqual(mesh.height_at(1, 0), (None, 0))


if __name__ == "__main__":
    unittest.main()
