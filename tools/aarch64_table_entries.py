#!/usr/bin/env python3
"""Read-only bounded AArch64 relative jump-table candidates from original ELF.

Resolve entries only when a verified adjacent ADRP/ADD table-base pair,
an ADR/LDRSW/ADD/BR dispatch and a local CMP/B.HI index bound agree.
Entries must be in nonwritable nonexecutable ELF PT_LOAD and computed
destinations must be aligned inside a known executable function range.

No code is executed and local bounds DO NOT prove all incoming paths guarded.
"""
import argparse
import json
import mmap
import re
import struct
import tempfile
import zipfile
from pathlib import Path

from aarch64_indirect_audit import parse_disassembly

ADRP = re.compile(r"^x([0-9]|[12][0-9]|30),\s*(0x[0-9a-fA-F]+)(?:\s.*)?$")
ADD = re.compile(r"^x([0-9]|[12][0-9]|30),\s*x([0-9]|[12][0-9]|30),\s*#(0x[0-9a-fA-F]+|\d+)(?:\s.*)?$")
MAX_ENTRIES = 64
MAX_LIBRARY = 320 * 1024 * 1024


def load_segments(data):
    if (len(data) < 64 or data[:4] != b"\x7fELF"
            or data[4:7] != b"\x02\x01\x01"
            or struct.unpack_from("<H", data, 18)[0] != 183):
        raise ValueError("expected little endian AArch64 ELF64")
    offset = struct.unpack_from("<Q", data, 32)[0]
    entries, count = struct.unpack_from("<HH", data, 54)
    if entries < 56 or count > 1024:
        raise ValueError("bad ELF program-header table")
    result = []
    for i in range(count):
        pos = offset + entries * i
        if pos > len(data) or pos + 56 > len(data):
            raise ValueError("ELF header out of bounds")
        typ, flags, fo, va, _, filesz, memsz, _ = struct.unpack_from("<IIQQQQQQ", data, pos)
        if typ != 1 or filesz == 0:
            continue
        if filesz > memsz or fo > len(data) or filesz > len(data)-fo:
            raise ValueError("invalid ELF LOAD segment")
        result.append({"flags":flags,"offset":fo,"va":va,"end":va+filesz})
    if not result:
        raise ValueError("no file-backed PT_LOAD segments")
    return result


def _unique_mapping(segments, address, size, required_flags, forbidden_flags):
    matches=[seg for seg in segments if seg["va"]<=address
             and address+size<=seg["end"]
             and seg["flags"] & required_flags == required_flags
             and seg["flags"] & forbidden_flags == 0]
    if len(matches)!=1:
        raise ValueError("ambiguous, unbacked or disallowed ELF mapping")
    seg=matches[0]
    return seg["offset"] + address - seg["va"]


def decode_table(data, segments, base, adr_pc, entries, fn_start, fn_end):
    if entries < 1 or entries > MAX_ENTRIES or base%4 or adr_pc%4:
        raise ValueError("table bound/address invalid")
    if fn_start%4 or fn_end<=fn_start or fn_end-fn_start>4*1024*1024:
        raise ValueError("function bounds invalid")
    table_offset=_unique_mapping(segments,base,entries*4,4,3) # readable, NOT writable or executable
    offsets=struct.unpack_from("<"+"i"*entries,data,table_offset)
    resolved=[]
    for i,relative in enumerate(offsets):
        pc=adr_pc+relative
        if pc%4 or not fn_start<=pc<fn_end:
            raise ValueError("candidate destination is not aligned or outside known function")
        _unique_mapping(segments,pc,4,1,2) # executable, not writable
        resolved.append({"index":i,"relative_offset_signed":relative,
                         "candidate_target":hex(pc)})
    return resolved


def inspect(elf, indirect, guard, llvm_disassembly, fn_size):
    if (indirect.get("architecture")!="AArch64" or
            guard.get("architecture")!="AArch64" or
            indirect.get("function")!=guard.get("function") or
            indirect.get("targets_resolved") is not False or
            guard.get("indirect_targets_resolved") is not False):
        raise ValueError("inconsistent input evidence")
    code=parse_disassembly(llvm_disassembly)
    sites={x["pc"]:x for x in indirect["sites"]}
    segments=load_segments(elf)
    start=int(indirect["entry"],16)
    end=start+fn_size
    outputs=[]
    for evidence in guard["sites"]:
        pc=int(evidence["pc"],16)
        site=sites.get(evidence["pc"])
        if site is None: raise ValueError("guard site absent from indirect inventory")
        row={"pc":hex(pc),"guard":evidence["local_guard"],"status":"UNRESOLVED",
             "all_incoming_paths_guarded":False,"targets_proven_executable_at_runtime":False}
        if (evidence["local_guard"]!="unsigned_index_upper_bound_candidate" or
                site["pattern"]!="pc_relative_indexed_table_dispatch_candidate"):
            row["reason"]="no_validated_local_index_guard"
            outputs.append(row);continue
        if (evidence.get("guard_branch_pc")!=hex(pc-24) or
                evidence.get("guard_compare_pc")!=hex(pc-28)):
            row["reason"]="index_guard_not_adjacent_to_adrp_add_pair"
            outputs.append(row);continue
        adr=pc-12
        p1=code.get(pc-20,("",""))
        p2=code.get(pc-16,("",""))
        m1=ADRP.fullmatch(p1[1]) if p1[0]=="adrp" else None
        m2=ADD.fullmatch(p2[1]) if p2[0]=="add" else None
        table_reg=site["table_base_register"]
        if not m1 or not m2 or not (
                "x"+m1[1]==table_reg==
                "x"+m2[1]=="x"+m2[2]):
            row["reason"]="missing_matching_adjacent_adrp_add_table_base"
            outputs.append(row);continue
        page=int(m1[2],16)
        low=int(m2[3],0)
        if page%4096 or low>4095:
            row["reason"]="invalid_adrp_add_page_offset"
            outputs.append(row);continue
        base=page+low
        entries=evidence["local_candidate_table_entries"]
        try:
            targets=decode_table(elf,segments,base,adr,entries,start,end)
        except (ValueError,struct.error) as exc:
            row["reason"]="table_mapping_or_candidate_rejected"
            row["detail"]=str(exc)
            outputs.append(row);continue
        row.update({"status":"STATIC_CANDIDATES",
                    "table_base":hex(base),"relative_to_pc":hex(adr),
                    "locally_bounded_entry_count":entries,
                    "candidate_entries":targets,
                    "evidence":"ADRP+ADD, ADR+LDRSW+ADD+BR, CMP+B.HI, read-only PT_LOAD",
                    "all_incoming_paths_guarded":False,
                    "targets_proven_executable_at_runtime":False})
        outputs.append(row)
    total=sum(len(r.get("candidate_entries",[])) for r in outputs)
    return {
        "architecture":"AArch64","function":indirect["function"],
        "status":"BOUNDED_AARCH64_STATIC_JUMP_TABLE_AUDIT",
        "site_count":len(outputs),
        "table_sites_with_static_candidates":sum(r["status"]=="STATIC_CANDIDATES" for r in outputs),
        "candidate_entry_count":total,
        "sites":outputs,
        "game_executed":False,
        "all_runtime_targets_confirmed":False,
        "limits":[
            "Only locally guarded and contiguous ADRP+ADD patterns resolve.",
            "Static targets are byte-derived candidates, not executed paths.",
            "Unrecognized paths/alternate entries may bypass the local bound.",
            "Only nonwritable read-only data and executable function-range destinations accepted.",
            "Never patches, injects or launches the original game."
        ]
    }


def inspect_apk(apk,indirect,guard,disasm,size,library="libloader.so"):
    with zipfile.ZipFile(apk) as z:
        m=z.getinfo("lib/arm64-v8a/"+library)
        if not 64<=m.file_size<=MAX_LIBRARY:
            raise ValueError("invalid ELF member size")
        with tempfile.TemporaryFile() as out:
            written=0
            with z.open(m) as inp:
                while True:
                    chunk=inp.read(1024*1024)
                    if not chunk:break
                    written+=len(chunk)
                    if written>m.file_size:raise ValueError("extraction overrun")
                    out.write(chunk)
            if written!=m.file_size:raise ValueError("truncated extraction")
            out.flush()
            with mmap.mmap(out.fileno(),0,access=mmap.ACCESS_READ) as data:
                return inspect(data,indirect,guard,disasm,size)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("apk",type=Path)
    p.add_argument("indirect_json",type=Path)
    p.add_argument("guard_json",type=Path)
    p.add_argument("llvm_disassembly",type=Path)
    p.add_argument("--function-size",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result=inspect_apk(a.apk,json.loads(a.indirect_json.read_text()),
        json.loads(a.guard_json.read_text()),a.llvm_disassembly.read_text(),a.function_size)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="sites"},indent=2))


if __name__=="__main__":main()
