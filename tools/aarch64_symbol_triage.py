#!/usr/bin/env python3
"""Read-only, exact substring triage of symbol names in the original AArch64 ELF.

A name match is never treated as confirmed gameplay logic or a runtime offset.
"""
import argparse
import hashlib
import json
import mmap
import tempfile
import zipfile
from pathlib import Path
from elf_inspect import inspect, ELFError

TERMS = ("camera", "player", "transform", "network", "position", "entity",
         "observer", "visibility", "unity", "il2cpp")
MAX_SIZE = 320*1024*1024


def triage(apk, *, library="libil2cpp.so", max_per_term=20):
    if library not in ("libil2cpp.so","libunity.so","libloader.so"):
        raise ValueError("unsupported library")
    if not 0 <= max_per_term <= 100:
        raise ValueError("max_per_term outside 0..100")
    with zipfile.ZipFile(apk) as archive:
        item = archive.getinfo("lib/arm64-v8a/" + library)
        if item.file_size < 64 or item.file_size > MAX_SIZE:
            raise ELFError("ELF member exceeds size budget")
        hashobj = hashlib.sha256()
        with tempfile.TemporaryFile() as target:
            size=0
            with archive.open(item) as reader:
                while True:
                    chunk=reader.read(1024*1024)
                    if not chunk: break
                    size+=len(chunk)
                    if size>item.file_size: raise ELFError("decompression overflow")
                    hashobj.update(chunk)
                    target.write(chunk)
            if size!=item.file_size: raise ELFError("truncated ZIP entry")
            target.flush()
            with mmap.mmap(target.fileno(), 0, access=mmap.ACCESS_READ) as data:
                report=inspect(data)
    if report["bits"]!=64 or report["machine"]!=183:
        raise ELFError("expected ARM64 library")
    names=report["functions"]
    terms={}
    for term in TERMS:
        hits=[{"name":f["name"],"address":f["address"],"size_bytes":f["size"]}
              for f in names if term in f["name"].lower()]
        terms[term]={"named_function_matches":len(hits),
                     "examples":hits[:max_per_term],
                     "examples_truncated":len(hits)>max_per_term}
    return {"status":"ARM64_ELF_SYMBOL_NAME_TRIAGE_PASS",
            "library":library,"library_bytes":size,"sha256":hashobj.hexdigest(),
            "named_function_symbols":len(names),"terms":terms,
            "all_query_terms":list(TERMS),"code_executed":False,
            "gameplay_functions_confirmed":0,
            "runtime_offsets_confirmed":0,
            "limitations":["Literal case-insensitive substring search of surviving STT_FUNC names.",
                           "A symbol mentioning player/camera is only a name hit, not a verified method.",
                           "Obfuscated, stripped, indirect and dynamically registered functions are missed.",
                           "No function instructions, Unity metadata, game state or player positions analyzed."]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("apk",type=Path)
    p.add_argument("--library",default="libil2cpp.so")
    p.add_argument("--max-per-term",type=int,default=20)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:r=triage(args.apk,library=args.library,max_per_term=args.max_per_term)
    except (OSError,ValueError,KeyError,zipfile.BadZipFile) as e:p.exit(2,f"error: {e}\n")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(r,indent=2)+"\n")
    print(json.dumps({k:v for k,v in r.items() if k!="terms"} |
                     {"term_counts":{k:v["named_function_matches"] for k,v in r["terms"].items()}},indent=2))


if __name__=="__main__":main()
