import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class AtomicFileHeaderTests(unittest.TestCase):
    def test_windows_header_does_not_export_min_max_macros(self):
        text = (ROOT / "include/edgeai/AtomicFile.hpp").read_text(encoding="utf-8")
        self.assertIn("#define NOMINMAX", text)
        define = text.index("#define NOMINMAX")
        include = text.index("#include <windows.h>")
        self.assertLess(define, include)


if __name__ == "__main__":
    unittest.main()
