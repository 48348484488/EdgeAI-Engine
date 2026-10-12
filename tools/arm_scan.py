#!/usr/bin/env python3
"""Conservative ARM32/Thumb16 direct branch scanner for executable ELF segments."""
import argparse
import json
from pathlib import Path
import struct

class ScanError(ValueError):
    pass

def checked(data, start, size):
    if start < 0 or size < 0 or start > len(data) or size > len(data) - start:
        raise ScanError("truncated or invalid ELF range")
    return data[start:start + size]

def signext(value, bits):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign

def exec_segments(data):
    if len(data) < 52 or data[:4] != b"\x7fELF" or data[4] != 1 or data[6] != 1:
        raise ScanError("requires ELF32")
    order = {1: "<", 2: ">"}.get(data[5])
    if order is None:
        raise ScanError("unsupported byte order")
    hdr = struct.unpack(order + "HHIIIIIHHHHHH", checked(data, 16, 36))
    machine, phoff, phentsize, phnum = hdr[1], hdr[4], hdr[8], hdr[9]
    if machine != 40:
        raise ScanError("requires ARM32 (EM_ARM=40)")
    if phnum and (phentsize < 32 or phnum > 4096):
        raise ScanError("invalid program header table")
    segments = []
    for i in range(phnum):
        p = struct.unpack(order + "IIIIIIII", checked(data, phoff + i * phentsize, 32))
        ptype, offset, vaddr, _, filesz, memsz, flags, _ = p
        if ptype == 1 and flags & 1 and filesz:
            checked(data, offset, filesz)
            if filesz > memsz:
                raise ScanError("invalid segment sizes")
            segments.append((offset, vaddr, filesz))
    return order, segments

def scan(data, mode="arm", limit=1000):
    if mode not in ("arm", "thumb") or limit < 0:
        raise ScanError("invalid mode or limit")
    order, segments = exec_segments(data)
    found = {}
    for off, base, length in segments:
        step = 4 if mode == "arm" else 2
        for i in range(0, length - step + 1, step):
            pc = base + i
            if mode == "arm":
                op = struct.unpack(order + "I", data[off + i:off + i + 4])[0]
                cond = (op >> 28) & 15
                if cond == 15 or ((op >> 25) & 7) != 5:
                    continue
                target = (pc + 8 + (signext(op & 0xffffff, 24) << 2)) & 0xffffffff
                kind = "BL" if op & (1 << 24) else "B"
            else:
                op = struct.unpack(order + "H", data[off + i:off + i + 2])[0]
                if op & 0xf800 == 0xe000:
                    target = (pc + 4 + (signext(op & 0x7ff, 11) << 1)) & 0xffffffff
                    kind = "B"
                elif op & 0xf000 == 0xd000 and ((op >> 8) & 15) < 14:
                    target = (pc + 4 + (signext(op & 0xff, 8) << 1)) & 0xffffffff
                    kind = "B.cond"
                else:
                    continue
            found[(pc, kind, target)] = {"address": f"0x{pc:x}", "instruction": kind, "target": f"0x{target:x}"}
    branches = [found[k] for k in sorted(found)]
    return {"architecture": "ARM32", "mode": mode, "executables_scanned": len(segments),
            "branch_count": len(branches), "truncated": len(branches) > limit,
            "branches": branches[:limit],
            "warning": "Raw branch candidates only. Mode is user-selected; code/data boundaries and function starts are NOT inferred."}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("file", type=Path)
    p.add_argument("--mode", choices=["arm", "thumb"], required=True,
                   help="ARM/Thumb mode must be established independently")
    p.add_argument("--max-branches", type=int, default=1000)
    args = p.parse_args()
    try:
        if args.file.stat().st_size > 128 * 1024 * 1024:
            raise ScanError("file exceeds 128 MiB")
        result = scan(args.file.read_bytes(), args.mode, args.max_branches)
    except (OSError, ScanError, struct.error) as e:
        p.exit(2, f"error: {e}\n")
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
