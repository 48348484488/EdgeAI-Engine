#!/usr/bin/env python3
"""Read-only ARM64 ELF inventory inside a split APK, using the EdgeAI ELF parser.

Streaming ZIP extraction + memory mapping allow inspecting large IL2CPP
libraries without executing them or requiring a GPU. Function addresses are
symbol metadata, NOT recovered function boundaries or game-state offsets.
"""
import argparse
import hashlib
import json
import mmap
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

from elf_inspect import ELFError, inspect

LIBRARIES = ("libil2cpp.so", "libunity.so", "libloader.so")
MAX_MEMBER = 320 * 1024 * 1024
MAX_APK = 200 * 1024 * 1024


def bounded(data, offset, size, max_size=16 * 1024 * 1024):
    if not (0 <= size <= max_size and 0 <= offset <= len(data)
            and size <= len(data) - offset):
        raise ELFError("invalid or excessive ELF table")
    return data[offset:offset + size]


def dynamic_info(data):
    """Extract DT_NEEDED and SONAME from validated ELF64 section metadata."""
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        raise ELFError("requires little-endian ELF64")
    if struct.unpack_from("<H", data, 18)[0] != 183:
        raise ELFError("requires AArch64 ELF (e_machine=183)")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    shentsize = struct.unpack_from("<H", data, 58)[0]
    shnum = struct.unpack_from("<H", data, 60)[0]
    if shnum > 32768 or (shnum and shentsize < 64):
        raise ELFError("invalid section headers")
    sections = []
    for i in range(shnum):
        offset = shoff + i * shentsize
        if offset > len(data) or 64 > len(data) - offset:
            raise ELFError("section header outside ELF")
        sections.append(struct.unpack_from("<IIQQQQIIQQ", data, offset))
    needed, soname = [], None
    for sec in sections:
        if sec[1] != 6:  # SHT_DYNAMIC
            continue
        if sec[6] >= len(sections) or sections[sec[6]][1] != 3:
            raise ELFError("dynamic section lacks linked string table")
        strsec = sections[sec[6]]
        strings = bounded(data, strsec[4], strsec[5])
        raw = bounded(data, sec[4], sec[5])
        if len(raw) % 16:
            raise ELFError("invalid SHT_DYNAMIC entry size")
        for pos in range(0, len(raw), 16):
            tag, value = struct.unpack_from("<qQ", raw, pos)
            if tag == 0:
                break
            if tag not in (1, 14):
                continue
            if value >= len(strings):
                raise ELFError("invalid DT_NEEDED/SONAME string offset")
            stop = strings.find(b"\0", value)
            if stop < 0:
                raise ELFError("unterminated dynamic string")
            name = strings[value:stop].decode("utf-8", "replace")
            if tag == 1 and name not in needed:
                needed.append(name)
            elif tag == 14:
                soname = name
    return {"needed": needed, "soname": soname}


def analyze_split(apk, *, max_functions=24, max_member=MAX_MEMBER):
    apk = Path(apk)
    if apk.stat().st_size > MAX_APK:
        raise ValueError("APK exceeds 200 MiB compressed size budget")
    libraries, errors = [], []
    with zipfile.ZipFile(apk) as archive:
        for name in LIBRARIES:
            members = [m for m in archive.infolist()
                       if m.filename == "lib/arm64-v8a/" + name]
            if len(members) != 1:
                errors.append({"library": name, "error": "expected one ARM64 entry"})
                continue
            item = members[0]
            if not 0 < item.file_size <= max_member:
                errors.append({"library": name, "error": "member exceeds allowed size"})
                continue
            sha = hashlib.sha256()
            with tempfile.TemporaryFile() as out:
                with archive.open(item) as stream:
                    total = 0
                    while True:
                        chunk = stream.read(1024 * 1024)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_member:
                            raise ValueError("decompression size limit exceeded")
                        sha.update(chunk)
                        out.write(chunk)
                if total != item.file_size:
                    raise ValueError("ZIP extraction length disagrees with directory")
                out.flush()
                try:
                    with mmap.mmap(out.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
                        report = inspect(mapped)
                        if report["bits"] != 64 or report["machine"] != 183:
                            raise ELFError("not ARM64 ELF")
                        dynamic = dynamic_info(mapped)
                except (ELFError, struct.error, ValueError) as exc:
                    errors.append({"library": name, "error": str(exc)})
                    continue
            symbols = report["functions"]
            libraries.append({
                "file": name,
                "bytes": total,
                "sha256": sha.hexdigest(),
                "architecture": "AArch64",
                "elf_type": report["type"],
                "entry": report["entry"],
                "section_count": report["section_count"],
                "named_function_symbols": report["function_count"],
                "function_symbol_sample": symbols[:max_functions],
                "function_sample_truncated": len(symbols) > max_functions,
                **dynamic,
            })
    return {
        "status": "ARM64_APK_STATIC_INVENTORY_PASS" if len(libraries) == 3 and not errors
                  else "ARM64_APK_STATIC_INVENTORY_INCOMPLETE",
        "apk_name": apk.name,
        "libraries": libraries,
        "errors": errors,
        "game_executed": False,
        "runtime_player_coordinates_verified": False,
        "limits": [
            "Read-only ELF section/symbol table inventory; no Android game was launched.",
            "Stripped binaries may contain zero named functions.",
            "A named symbol is not a reconstructed function or an ESP address.",
            "Dynamic dependencies are parsed from ELF SHT_DYNAMIC when present.",
            "No code disassembly, ARM64 dataflow, gameplay camera mapping, or decompilation."
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("apk", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--max-functions", type=int, default=24)
    args = p.parse_args()
    if not 0 <= args.max_functions <= 1000:
        p.error("--max-functions must be within 0..1000")
    try:
        report = analyze_split(args.apk, max_functions=args.max_functions)
    except (OSError, ValueError, zipfile.BadZipFile, EOFError, struct.error) as exc:
        p.exit(2, f"error: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k != "libraries"} |
                     {"libraries": [{k:v for k,v in x.items() if k != "function_symbol_sample"}
                                    for x in report["libraries"]]}, indent=2))
    if report["status"] != "ARM64_APK_STATIC_INVENTORY_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
