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

    def test_flat_frame_detection_and_alpha_independence(self):
        with tempfile.TemporaryDirectory() as tmp:
            flat, multi = Path(tmp)/'flat.png', Path(tmp)/'multi.png'
            png(flat, 4, 4, [bytes([68, 115, 52]*4)]*4)
            rows = []
            for y in range(4):
                row = bytearray()
                for x in range(4):
                    row.extend((x*20, y*30, (x+y)*15, 255))
                rows.append(bytes(row))
            png(multi, 4, 4, rows, color=6)
            self.assertFalse(module.inspect_frame(flat)['nonflat_frame'])
            self.assertEqual(module.inspect_frame(flat)['distinct_rgb_colors_at_least'], 1)
            self.assertTrue(module.inspect_frame(multi)['nonflat_frame'])
            report = module.compare(flat, multi)
            self.assertFalse(report['reference_frame']['nonflat_frame'])
            self.assertTrue(report['candidate_frame']['nonflat_frame'])
            self.assertFalse(report['parity_proven'])

    def test_color_gate_rejects_invalid_threshold(self):
        with self.assertRaisesRegex(ValueError, 'min_distinct_colors'):
            module.frame_statistics(1, 1, bytes([0, 0, 0, 255]), 1)

    def test_packed_alpha_mask_warning_and_hidden_rgb(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp)/'packed.png'
            row = bytes([10,20,30,0, 40,50,60,0,
                         70,80,90,0, 0,0,0,255])
            png(a, 4, 1, [row], color=6)
            report = module.inspect_alpha(a)
            self.assertEqual(report['alpha_zero_pixels'], 3)
            self.assertEqual(report['nonzero_rgb_under_zero_alpha_pixels'], 3)
            self.assertEqual(report['alpha_zero_fraction'], .75)
            self.assertTrue(report['possible_packed_material_mask'])
            self.assertFalse(report['original_shader_semantics_proven'])

    def test_rgb_has_opaque_alpha_and_invalid_buffer_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp)/'rgb.png'
            png(a, 1, 1, [bytes([12,34,56])])
            report = module.inspect_alpha(a)
            self.assertEqual(report['alpha_opaque_pixels'], 1)
            self.assertFalse(report['possible_packed_material_mask'])
        with self.assertRaisesRegex(ValueError, 'RGBA pixel buffer'):
            module.alpha_statistics(2, 2, bytes(3))

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
