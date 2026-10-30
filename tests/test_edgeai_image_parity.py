"""Tests for screenshot parity without external image dependencies."""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
import importlib.util

SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'edgeai_image_parity.py'
spec = importlib.util.spec_from_file_location('edgeai_image_parity', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def png(path, width, height, rows, color=2, filter_type=0):
    def chunk(name, payload):
        return struct.pack('>I', len(payload)) + name + payload + struct.pack('>I', zlib.crc32(name + payload) & 0xffffffff)
    raw = b''.join(bytes([filter_type]) + row for row in rows)
    path.write_bytes(module.PNG_SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, color, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


class ImageParityTests(unittest.TestCase):
    def test_identical_rgb_and_rgba(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a.png', Path(tmp)/'b.png'
            png(a, 2, 1, [bytes([5, 10, 15, 20, 25, 30])])
            png(b, 2, 1, [bytes([5, 10, 15, 255, 20, 25, 30, 1])], color=6)
            self.assertEqual(module.compare(a, b)['changed_pixels'], 0)

    def test_changed_bbox_and_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a.png', Path(tmp)/'b.png'
            png(a, 2, 2, [bytes(6), bytes(6)])
            png(b, 2, 2, [bytes(6), bytes([0, 0, 0, 10, 0, 0])])
            result = module.compare(a, b)
            self.assertEqual(result['difference_bbox_xyxy_inclusive'], [1, 1, 1, 1])
            self.assertEqual(result['changed_pixel_fraction'], .25)
            self.assertEqual(module.compare(a, b, 10)['changed_pixels'], 0)

    def test_resolution_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'a.png', Path(tmp)/'b.png'
            png(a, 1, 1, [bytes(3)])
            png(b, 2, 1, [bytes(6)])
            with self.assertRaisesRegex(ValueError, 'resolution mismatch'):
                module.compare(a, b)

    def test_crc_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp)/'a.png'
            png(a, 1, 1, [bytes(3)])
            corrupted = bytearray(a.read_bytes())
            corrupted[-8] ^= 1
            a.write_bytes(corrupted)
            with self.assertRaisesRegex(ValueError, 'CRC'):
                module.read_png(a)

    def test_png_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            for f in range(5):
                a = Path(tmp)/f'{f}.png'
                png(a, 1, 1, [bytes([3, 5, 7])], filter_type=f)
                self.assertEqual(module.read_png(a)[:2], (1, 1))


if __name__ == '__main__':
    unittest.main()
