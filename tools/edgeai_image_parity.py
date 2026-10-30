#!/usr/bin/env python3
"""Compare real PNG screenshots at identical resolution using only Python stdlib.

Strict, lossless RGB/RGBA 8-bit non-interlaced PNG input. Reject unsupported
formats rather than silently resampling or producing misleading parity claims.
"""
import argparse
import json
import struct
import zlib
from pathlib import Path

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def read_png(path):
    data = Path(path).read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError('not a PNG file')
    pos = len(PNG_SIGNATURE)
    ihdr = None
    chunks = []
    seen_end = False
    while pos < len(data):
        if len(data) - pos < 12:
            raise ValueError('truncated PNG chunk')
        size = struct.unpack_from('>I', data, pos)[0]
        kind = data[pos+4:pos+8]
        end = pos + 12 + size
        if end > len(data):
            raise ValueError('truncated PNG chunk payload')
        payload = data[pos+8:pos+8+size]
        crc = struct.unpack_from('>I', data, pos+8+size)[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError('PNG CRC mismatch')
        pos = end
        if kind == b'IHDR':
            if ihdr is not None or size != 13:
                raise ValueError('invalid PNG IHDR')
            ihdr = struct.unpack('>IIBBBBB', payload)
        elif kind == b'IDAT':
            chunks.append(payload)
        elif kind == b'IEND':
            seen_end = True
            break
        elif kind in (b'PLTE', b'tRNS'):
            raise ValueError('palette/transparency PNG unsupported')
    if not seen_end or ihdr is None or not chunks:
        raise ValueError('incomplete PNG')
    width, height, depth, color, compression, filtering, interlace = ihdr
    if width == 0 or height == 0 or depth != 8 or color not in (2, 6) or (compression, filtering, interlace) != (0, 0, 0):
        raise ValueError('requires 8-bit RGB/RGBA non-interlaced PNG')
    channels = 3 if color == 2 else 4
    stride = width * channels
    expected = height * (stride + 1)
    raw = zlib.decompress(b''.join(chunks))
    if len(raw) != expected:
        raise ValueError('unexpected decompressed PNG size')
    previous = bytearray(stride)
    pixels = bytearray()
    offset = 0
    for _ in range(height):
        method = raw[offset]
        row = bytearray(raw[offset+1:offset+1+stride])
        offset += stride + 1
        if method > 4:
            raise ValueError('invalid PNG filter')
        for i in range(stride):
            a = row[i-channels] if i >= channels else 0
            b = previous[i]
            c = previous[i-channels] if i >= channels else 0
            if method == 1:
                prediction = a
            elif method == 2:
                prediction = b
            elif method == 3:
                prediction = (a+b)//2
            elif method == 4:
                p = a+b-c
                pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                prediction = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
            else:
                prediction = 0
            row[i] = (row[i] + prediction) & 255
        if channels == 3:
            for i in range(0, stride, 3):
                pixels.extend(row[i:i+3])
                pixels.append(255)
        else:
            pixels.extend(row)
        previous = row
    return width, height, bytes(pixels)


def compare(reference, candidate, threshold=0):
    if not 0 <= threshold <= 255:
        raise ValueError('threshold must be in [0,255]')
    rw, rh, rp = read_png(reference)
    cw, ch, cp = read_png(candidate)
    if (rw, rh) != (cw, ch):
        raise ValueError(f'resolution mismatch: {rw}x{rh} vs {cw}x{ch}; align captures before comparison')
    changed = 0
    total_error = 0
    max_error = 0
    bbox = [rw, rh, -1, -1]
    for idx in range(rw*rh):
        i = idx*4
        diffs = [abs(rp[i+k]-cp[i+k]) for k in range(3)]
        total_error += sum(diffs)
        max_error = max(max_error, *diffs)
        if max(diffs) > threshold:
            changed += 1
            x, y = idx % rw, idx // rw
            bbox = [min(bbox[0], x), min(bbox[1], y), max(bbox[2], x), max(bbox[3], y)]
    return {
        'width': rw, 'height': rh, 'threshold_per_channel': threshold,
        'changed_pixels': changed, 'changed_pixel_fraction': changed/(rw*rh),
        'mean_absolute_rgb_error': total_error/(rw*rh*3),
        'max_channel_error': max_error,
        'difference_bbox_xyxy_inclusive': bbox if changed else None,
        'parity_proven': False,
        'note': 'Pixel metrics only; matching pixels do not prove equivalent gameplay, controls, or timing.',
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference', type=Path)
    p.add_argument('candidate', type=Path)
    p.add_argument('--threshold', type=int, default=0)
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    result = compare(args.reference, args.candidate, args.threshold)
    payload = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding='utf-8')
    print(payload, end='')


if __name__ == '__main__':
    main()
