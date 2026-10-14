#!/usr/bin/env python3
"""Conservative *local* AArch64 jump-table guard evidence from LLVM.

Only consecutive CMP Widx,#imm -> B.HI -> optional ADRP/ADD -> ADR ->
LDRSW -> ADD -> BR is accepted. This validates a local instruction
shape, NOT path feasibility, all entry points, or indirect targets.
"""
import argparse
import json
import re
from pathlib import Path
from aarch64_indirect_audit import parse_disassembly

CMP = re.compile(r"w(\d{1,2}),\s*#(0x[0-9a-f]+|\d+)$")
BHI = re.compile(r"0x([0-9a-f]+)(?:\s.*)?$", re.I)
ADRP = re.compile(r"x(\d{1,2}),\s*0x[0-9a-f]+(?:\s.*)?$", re.I)
ADD = re.compile(r"x(\d{1,2}),\s*x(\d{1,2}),\s*#(?:0x[0-9a-f]+|\d+)(?:\s.*)?$", re.I)


def local_guard(site, code):
    pc=int(site["pc"],16)
    idx=site["index_register"]
    table_base=site["table_base_register"]
    if not re.fullmatch(r"x(?:[12]?\d|30)",idx) or not re.fullmatch(r"x(?:[12]?\d|30)",table_base):
        raise ValueError("invalid register")
    adr_pc=pc-12
    if "evidence_pcs" not in site or site["evidence_pcs"] != [hex(pc-k) for k in (12,8,4,0)]:
        raise ValueError("missing consecutive table pattern evidence")
    cursor=adr_pc-4
    # Two approved ways to materialize the table base immediately before ADR.
    # ADRP + ADD must agree on the exact table base register, otherwise stop.
    ad=code.get(cursor)
    if ad and ad[0]=="add":
        ma=ADD.fullmatch(ad[1])
        if ma and ("x"+ma[1]) == table_base and ma[1]==ma[2]:
            prev=code.get(cursor-4)
            mp=ADRP.fullmatch(prev[1]) if prev and prev[0]=="adrp" else None
            if not mp or "x"+mp[1]!=table_base:
                return {"local_guard":"unverified","reason":"incomplete_table_base_pair"}
            cursor-=8
    # The exact next instruction is B.HI, and immediately preceding is CMP.
    branch=code.get(cursor)
    if branch is None or branch[0]!="b.hi":
        return {"local_guard":"unverified","reason":"no_adjacent_unsigned_bhi"}
    bt=BHI.fullmatch(branch[1])
    cmp=code.get(cursor-4)
    match=CMP.fullmatch(cmp[1]) if cmp and cmp[0]=="cmp" else None
    if not bt or not match or "x"+match[1]!=idx:
        return {"local_guard":"unverified","reason":"comparison_or_guard_mismatch"}
    upper=int(match[2],0)
    escape=int(bt[1],16)
    if not 0<=upper<=256 or escape<=pc or escape%4:
        return {"local_guard":"unverified","reason":"upper_bound_or_escape_not_proven"}
    return {
        "local_guard":"unsigned_index_upper_bound_candidate",
        "guard_compare_pc":hex(cursor-4),
        "guard_branch_pc":hex(cursor),
        "guard_escape_pc":hex(escape),
        "index_register":idx,
        "local_unsigned_index_max_inclusive":upper,
        "local_candidate_table_entries":upper+1,
        "all_incoming_paths_guarded":False,
        "target_entries_resolved":False,
    }


def analyze(dispatch, disassembly):
    if dispatch.get("architecture")!="AArch64" or dispatch.get("targets_resolved") is not False:
        raise ValueError("requires unresolved AArch64 indirect audit")
    code=parse_disassembly(disassembly)
    records=[]
    for site in dispatch["sites"]:
        record={"pc":site["pc"],"pattern":site["pattern"]}
        if site["pattern"]=="pc_relative_indexed_table_dispatch_candidate":
            record.update(local_guard(site,code))
        else:
            record.update({"local_guard":"unverified","reason":"not_a_relative_table_dispatch"})
        records.append(record)
    known=sum(r["local_guard"]=="unsigned_index_upper_bound_candidate" for r in records)
    return {
        "architecture":"AArch64",
        "function":dispatch["function"],
        "dispatch_site_count":len(records),
        "locally_guarded_table_dispatch_sites":known,
        "unverified_or_nontable_sites":len(records)-known,
        "sites":records,
        "jump_table_bytes_read":False,
        "indirect_targets_resolved":False,
        "path_feasibility_proven":False,
        "original_game_executed":False,
        "limitations":[
            "Local CMP + B.HI upper bound only, no global path proof.",
            "Unsigned CMP on index register only, conservative contiguous syntax.",
            "Does not read table offsets, resolve destinations or prove loop iteration.",
            "Index may be modified through other entry paths not captured by the local window.",
            "No gameplay camera, player location or bypass inference."
        ],
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("dispatch_json",type=Path)
    p.add_argument("llvm_disassembly",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result=analyze(json.loads(a.dispatch_json.read_text()),a.llvm_disassembly.read_text())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="sites"},indent=2))


if __name__=="__main__":main()
