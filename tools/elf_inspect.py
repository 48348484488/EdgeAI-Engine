#!/usr/bin/env python3
"""Read-only ELF function-symbol inventory; no third-party packages."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

class ELFError(ValueError):
    pass

def region(data, offset, length):
    if offset < 0 or length < 0 or offset > len(data) or length > len(data)-offset:
        raise ELFError("range exceeds file")
    return data[offset:offset+length]

def inspect(data):
    if len(data) < 16 or data[:4] != b"\x7fELF":
        raise ELFError("not an ELF")
    bits = {1:32, 2:64}.get(data[4])
    endian = {1:"<", 2:">"}.get(data[5])
    if not bits or not endian or data[6] != 1:
        raise ELFError("unsupported ELF identification")
    hf = endian + ("HHIIIIIHHHHHH" if bits == 32 else "HHIQQQIHHHHHH")
    fields = struct.unpack(hf, region(data, 16, struct.calcsize(hf)))
    e_type, machine, version, entry, phoff, shoff, flags, ehsize, phentsize, phnum, shentsize, shnum, shstr = fields
    if version != 1 or ehsize < 16 + struct.calcsize(hf):
        raise ELFError("invalid ELF header")
    sf = endian + ("IIIIIIIIII" if bits == 32 else "IIQQQQIIQQ")
    ss = struct.calcsize(sf)
    if shnum and (not shoff or shentsize < ss or shnum > 1000000):
        raise ELFError("invalid section table")
    sections = [struct.unpack(sf, region(data, shoff+i*shentsize, ss)) for i in range(shnum)]
    def section_bytes(i):
        if i >= len(sections):
            raise ELFError("invalid linked section index")
        return region(data, sections[i][4], sections[i][5])
    symfmt = endian + ("IIIBBH" if bits == 32 else "IBBHQQ")
    symsize = struct.calcsize(symfmt)
    found = {}
    for i,s in enumerate(sections):
        if s[1] not in (2,11):
            continue
        if not s[9] or s[9] < symsize or s[5] % s[9] or s[5]//s[9] > 1000000:
            raise ELFError("invalid symbol table")
        strings = section_bytes(s[6])
        if sections[s[6]][1] != 3:
            raise ELFError("linked section is not a string table")
        raw = section_bytes(i)
        for off in range(0,len(raw),s[9]):
            f = struct.unpack(symfmt,raw[off:off+symsize])
            if bits == 32:
                name_off, value, size, info, other, shndx = f
            else:
                name_off, info, other, shndx, value, size = f
            if (info & 15) != 2 or shndx == 0:
                continue
            if name_off >= len(strings):
                raise ELFError("symbol name outside string table")
            end = strings.find(b"\x00",name_off)
            if end < 0:
                raise ELFError("unterminated function name")
            name = strings[name_off:end].decode("utf-8",errors="replace")
            if name:
                found[(name,value,size)] = {"name":name,"address":f"0x{value:x}","size":size,"source":"symtab" if s[1]==2 else "dynsym"}
    functions = [found[k] for k in sorted(found,key=lambda k:(k[1],k[0]))]
    return {"format":"ELF","bits":bits,"endianness":"little" if endian=="<" else "big",
            "machine":machine,"type":e_type,"entry":f"0x{entry:x}",
            "section_count":shnum,"function_count":len(functions),"functions":functions,
            "limitations":["Only defined named STT_FUNC symbols are reported.",
                           "Stripped binaries may report zero functions.",
                           "No disassembly or C++ recovery is performed."]}

def main():
    parser = argparse.ArgumentParser(description="Inspect named ELF function symbols")
    parser.add_argument("file",type=Path)
    parser.add_argument("--max-functions",type=int,default=1000)
    args = parser.parse_args()
    if args.max_functions < 0:
        parser.error("--max-functions must be nonnegative")
    try:
        if args.file.stat().st_size > 128*1024*1024:
            raise ELFError("file exceeds 128 MiB limit")
        data = args.file.read_bytes()
        result = inspect(data)
        result["sha256"] = hashlib.sha256(data).hexdigest()
        result["functions_truncated"] = len(result["functions"]) > args.max_functions
        result["functions"] = result["functions"][:args.max_functions]
    except (OSError,ELFError,struct.error) as exc:
        parser.exit(2,f"error: {exc}\n")
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__ == "__main__":
    main()
