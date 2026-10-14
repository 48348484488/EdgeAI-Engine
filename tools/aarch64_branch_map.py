#!/usr/bin/env python3
"""Conservative AArch64 direct-branch inventory of one named ELF64 function.

Intended for static evidence on compiled, authorized ELF inputs. No executable
code is run, and a branch candidate is not semantic recovery or bypass proof.
"""
import argparse
import json
import mmap
import struct
import zipfile
import tempfile
from pathlib import Path

from elf_inspect import inspect, ELFError


def sign_extend(v, bits):
    return (v ^ (1 << (bits - 1))) - (1 << (bits - 1))


def decode(word, pc):
    """Decode selected fixed-width AArch64 control transfers, no guesswork."""
    if word & 0x7c000000 == 0x14000000:
        kind = "BL" if word & 0x80000000 else "B"
        imm26 = sign_extend(word & 0x03ffffff, 26)
        return {"kind": kind, "target": pc + imm26 * 4}
    if word & 0xff000010 == 0x54000000:
        cond = word & 15
        if cond >= 14:
            return None
        return {"kind": "B.cond", "target": pc + sign_extend((word >> 5) & 0x7ffff, 19) * 4,
                "condition": cond}
    if word & 0x7e000000 == 0x34000000:
        return {"kind": "CBNZ" if word & 0x01000000 else "CBZ",
                "target": pc + sign_extend((word >> 5) & 0x7ffff, 19) * 4}
    if word & 0x7e000000 == 0x36000000:
        return {"kind": "TBNZ" if word & 0x01000000 else "TBZ",
                "target": pc + sign_extend((word >> 5) & 0x3fff, 14) * 4}
    if word & 0xfffffc1f == 0xd65f0000:
        return {"kind": "RET", "target": None}
    if word & 0xfffffc1f == 0xd61f0000:
        return {"kind": "BR", "target": None}
    if word & 0xfffffc1f == 0xd63f0000:
        return {"kind": "BLR", "target": None}
    return None


def exec_loads(data):
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4:7] != b"\x02\x01\x01":
        raise ELFError("expected little-endian ELF64")
    if struct.unpack_from("<H", data, 18)[0] != 183:
        raise ELFError("expected e_machine 183 (AArch64)")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    entsize, count = struct.unpack_from("<HH", data, 54)
    if count > 4096 or (count and entsize < 56):
        raise ELFError("invalid ELF64 program headers")
    regions = []
    for i in range(count):
        off = phoff + i * entsize
        if off > len(data) or 56 > len(data) - off:
            raise ELFError("program header extends beyond ELF")
        typ, flags, fileoff, va, _, filesz, memsz, _ = struct.unpack_from("<IIQQQQQQ",data,off)
        if typ != 1 or not (flags & 1) or not filesz:
            continue
        if filesz > memsz or fileoff > len(data) or filesz > len(data) - fileoff:
            raise ELFError("invalid executable LOAD segment")
        regions.append((va, va + filesz, fileoff))
    if not regions:
        raise ELFError("no executable ELF LOAD segment")
    return regions


def map_address(regions, data, pc):
    choices = [fo + pc - lo for lo, hi, fo in regions if lo <= pc and pc + 4 <= hi]
    if len(choices) != 1:
        raise ELFError("ambiguous or unmapped executable address " + hex(pc))
    off = choices[0]
    if off > len(data) or len(data) - off < 4:
        raise ELFError("instruction outside file")
    return off


def analyze(data, function, max_results=120):
    if not 0 <= max_results <= 1000:
        raise ValueError("max_results must be 0..1000")
    report = inspect(data)
    if report["bits"] != 64 or report["machine"] != 183:
        raise ELFError("AArch64 ELF64 required")
    matches = [f for f in report["functions"] if f["name"] == function]
    if len(matches) != 1:
        raise ELFError("expected exactly one named function: " + function)
    sym = matches[0]
    entry = int(sym["address"], 16)
    size = sym["size"]
    if entry & 3 or size < 4 or size > 4*1024*1024 or size % 4:
        raise ELFError("unusable function size or alignment")
    regions = exec_loads(data)
    counters, edges = {}, []
    for pc in range(entry, entry+size, 4):
        word = struct.unpack_from("<I", data, map_address(regions,data,pc))[0]
        instruction = decode(word,pc)
        if instruction is None:
            continue
        kind = instruction["kind"]
        counters[kind] = counters.get(kind, 0) + 1
        target = instruction.get("target")
        edges.append({"pc": hex(pc), "kind": kind,
                      "target": hex(target) if target is not None else None,
                      "target_in_symbol": entry <= target < entry+size if target is not None else None})
    return {
        "architecture": "AArch64", "function": function,
        "entry": hex(entry), "size_bytes": size,
        "decoded_control_transfers": len(edges), "counts": counters,
        "control_transfer_candidates": edges[:max_results],
        "sample_truncated": len(edges)>max_results,
        "code_executed": False,
        "limitations": [
            "Linear 4-byte scan of a symbol's declared size; inline data can yield false positives.",
            "Selected direct AArch64 B/BL/B.cond/CBZ/TBZ and RET/BR/BLR only.",
            "Does not prove target reachability, calls, ABI contracts, game logic or decompilation.",
            "No Android runtime or protection bypass performed."
        ]
    }


def analyze_split(apk, name="libloader.so", function="JNI_OnLoad", max_results=120):
    with zipfile.ZipFile(apk) as z:
        item = z.getinfo("lib/arm64-v8a/" + name)
        if item.file_size < 64 or item.file_size > 320*1024*1024:
            raise ELFError("library size outside budget")
        with tempfile.TemporaryFile() as tmp:
            with z.open(item) as f:
                n = 0
                while True:
                    chunk = f.read(1024*1024)
                    if not chunk:
                        break
                    n += len(chunk)
                    if n > item.file_size: raise ELFError("ZIP member exceeded announced size")
                    tmp.write(chunk)
            if n != item.file_size:
                raise ELFError("incomplete member extraction")
            tmp.flush()
            with mmap.mmap(tmp.fileno(), 0, access=mmap.ACCESS_READ) as data:
                return analyze(data, function, max_results)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("apk",type=Path)
    p.add_argument("--library",default="libloader.so",choices=["libloader.so","libunity.so","libil2cpp.so"])
    p.add_argument("--function",default="JNI_OnLoad")
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--max-results",type=int,default=120)
    args=p.parse_args()
    try:
        result=analyze_split(args.apk,args.library,args.function,args.max_results)
    except (OSError,ValueError,struct.error,zipfile.BadZipFile,KeyError) as exc:
        p.exit(2,f"error: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="control_transfer_candidates"},indent=2))


if __name__=="__main__":main()
