#!/usr/bin/env python3
"""Forensic, explicitly UNPROVEN AArch64 ELF jump-table snapshots.

Read table bytes for a locally guarded dispatch with a lexically preceding
ADRP/ADD origin even if that origin is not adjacent to the dispatch.  Unlike
a resolved CFG, this only gives static byte-derived hypotheses; all incoming
control-flow paths reaching the register value remain unverified.
"""
import argparse
import json
import mmap
import re
import tempfile
import zipfile
from pathlib import Path
from aarch64_table_entries import decode_table, load_segments
from aarch64_indirect_audit import parse_disassembly
from aarch64_table_provenance import may_write_register, reg_id, ADRP, IMM_ADD

MAX_LIBRARY=320*1024*1024
MAX_SPAN=256


def inspect(elf, indirect, bounds, provenance, graph, disassembly, fn_size):
    if (indirect.get("architecture")!="AArch64" or
        bounds.get("architecture")!="AArch64" or
        provenance.get("architecture")!="AArch64" or
        graph.get("architecture")!="AArch64" or
        len({indirect.get("function"),bounds.get("function"),
             provenance.get("function"),graph.get("function")})!=1 or
        indirect.get("targets_resolved") is not False or
        bounds.get("indirect_targets_resolved") is not False or
        provenance.get("indirect_targets_resolved") is not False or
        graph.get("code_executed") is not False):
        raise ValueError("inconsistent read-only AArch64 evidence")
    code=parse_disassembly(disassembly)
    segments=load_segments(elf)
    start=int(indirect["entry"],16)
    end=start+fn_size
    if int(graph["entry"],16)!=start or graph["symbol_size_bytes"]!=fn_size:
        raise ValueError("CFG and function size mismatch")
    leaders={int(b["start"],16) for b in graph["blocks"]}
    valid_br={int(b["last_instruction"],16) for b in graph["blocks"]
              if b["last_control_transfer"]=="BR"}
    orig={s["pc"]:s for s in indirect["sites"]}
    prov={s["pc"]:s for s in provenance["sites"]}
    found=[]
    for g in bounds["sites"]:
        pc=int(g["pc"],16)
        row={"pc":hex(pc),"status":"UNRESOLVED","runtime_reaching_definition_proven":False,
             "runtime_targets_confirmed":False}
        site=orig.get(g["pc"])
        p=prov.get(g["pc"])
        if site is None or p is None:
            raise ValueError("missing site in independent evidence")
        if (g.get("local_guard")!="unsigned_index_upper_bound_candidate" or
            site.get("pattern")!="pc_relative_indexed_table_dispatch_candidate" or
            p.get("status")!="TEXTUAL_ADRP_ADD_CANDIDATE"):
            row["reason"]="no_guard_or_lexical_base"
            found.append(row);continue
        if pc not in valid_br or code.get(pc,("",""))[0]!="br":
            raise ValueError("selected indirect jump is not a block tail BR")
        if site.get("table_base_register")!=p.get("table_base_register") or (
                site.get("index_register")!=g.get("index_register")):
            raise ValueError("register mismatch between independent evidence")
        entries=g["local_candidate_table_entries"]
        if not isinstance(entries,int) or not 1<=entries<=64 or (
                g["local_unsigned_index_max_inclusive"]!=entries-1):
            raise ValueError("invalid guard bounds")
        if (g.get("guard_compare_pc")!=hex(pc-20) or
            g.get("guard_branch_pc")!=hex(pc-16)):
            row["reason"]="nonadjacent_guard"
            found.append(row);continue
        # Reject altered/untrusted LLVM at the guard, base, and dispatch sites.
        cmp_op,cmp_args=code.get(pc-20,("",""))
        branch_op,_=code.get(pc-16,("",""))
        if (cmp_op!="cmp" or
            not re.fullmatch(r"w([0-9]|[12][0-9]|30),\s*#(0x[0-9a-fA-F]+|\d+)",cmp_args) or
            branch_op!="b.hi"):
            raise ValueError("LLVM guard mismatch")
        idx=cmp_args.split(",",1)[0]
        if idx!="w"+g["index_register"][1:] or int(cmp_args.split("#",1)[1],0)!=entries-1:
            raise ValueError("LLVM guard index mismatch")
        reg=reg_id(site["table_base_register"])
        if reg is None or reg!=reg_id(p["table_base_register"]):
            raise ValueError("invalid base register")
        adrp_pc=int(p["adrp_pc"],16)
        add_pc=int(p["add_pc"],16)
        if not (start<=adrp_pc<add_pc<pc<=end-4) or pc-add_pc>4*MAX_SPAN:
            row["reason"]="provenance_gap_too_long"
            found.append(row);continue
        adrop,adrargs=code.get(adrp_pc,("",""))
        addop,addargs=code.get(add_pc,("",""))
        ap=ADRP.fullmatch(adrargs) if adrop=="adrp" else None
        ma=IMM_ADD.fullmatch(addargs) if addop=="add" else None
        if not ap or not ma or not (int(ap[1])==reg==int(ma[1])==int(ma[2])):
            raise ValueError("LLVM ADRP/ADD base origin mismatch")
        base=int(ap[2],16)+int(ma[3],0)
        if base!=int(p["table_base_candidate"],16):
            raise ValueError("base origin not reproducible")
        if not (0<=int(ma[3],0)<4096 and int(ap[2],16)%4096==0):
            raise ValueError("unaligned base origin")
        # Any observed clobber along the textual interval, including a caller-
        # saved register across a call, disqualifies even a forensic snapshot.
        bad=[]
        for at in range(add_pc+4,pc,4):
            op,args=code.get(at,("",""))
            if not op:
                bad.append(at)
            if may_write_register(op,args,reg):
                bad.append(at)
            if op in ("bl","blr") and (reg<=18 or reg==30):
                bad.append(at)
        if bad:
            row["reason"]="possible_base_clobber_or_incomplete_instruction_stream"
            row["hazard_addresses"]=[hex(a) for a in sorted(set(bad))[:8]]
            found.append(row);continue
        adr_pc=pc-12
        if (code.get(adr_pc,("",""))[0]!="adr" or
            code.get(pc-8,("",""))[0]!="ldrsw" or
            code.get(pc-4,("",""))[0]!="add"):
            raise ValueError("indirect dispatch LLVM shape invalid")
        try:
            candidates=decode_table(elf,segments,base,adr_pc,entries,start,end)
        except ValueError as exc:
            row["reason"]="table_bytes_or_targets_rejected"
            row["detail"]=str(exc)
            found.append(row);continue
        if any(int(x["candidate_target"],16) not in leaders for x in candidates):
            row["reason"]="targets_not_at_existing_cfg_block_leaders"
            found.append(row);continue
        row.update({
            "status":"FORENSIC_STATIC_BYTES_NO_REACHING_DEFINITION_PROOF",
            "table_base":hex(base),"relative_to_pc":hex(adr_pc),
            "entry_count":entries,"entries":candidates,
            "intervening_transfer_count":p.get("intervening_transfer_count",0),
            "table_data_read_only":True,
            "target_bytes_in_executable_symbol":True,
            "cfg_edge_promotion_authorized":False,
            "runtime_reaching_definition_proven":False,
            "runtime_targets_confirmed":False,
        })
        found.append(row)
    accepted=[s for s in found if s["status"]=="FORENSIC_STATIC_BYTES_NO_REACHING_DEFINITION_PROOF"]
    return {"status":"EDGEAI_ARM64_FORENSIC_JUMP_TABLE_SNAPSHOT",
            "function":indirect["function"],"architecture":"AArch64",
            "sites_checked":len(found),"forensic_tables":len(accepted),
            "forensic_entries":sum(s["entry_count"] for s in accepted),
            "sites":found,"cfg_modified":False,
            "original_game_executed":False,
            "runtime_paths_proven":False,
            "limitations":[
                "Lexical ADRP/ADD register origins are not dataflow proofs on all CFG paths.",
                "Table bytes/targets can be plausible but not necessarily used at runtime.",
                "No candidate is promoted to a CFG edge or gameplay/ESP signal.",
            ]}


def inspect_apk(apk, indirect, bounds, provenance, graph, disassembly, size):
    with zipfile.ZipFile(apk) as archive:
        member=archive.getinfo("lib/arm64-v8a/libloader.so")
        if not 64<=member.file_size<=MAX_LIBRARY:
            raise ValueError("invalid ELF size")
        with tempfile.TemporaryFile() as output:
            with archive.open(member) as src:
                size_read=0
                while True:
                    block=src.read(1024*1024)
                    if not block: break
                    size_read+=len(block)
                    if size_read>member.file_size: raise ValueError("ELF length overrun")
                    output.write(block)
            if size_read!=member.file_size:raise ValueError("truncated ELF")
            output.flush()
            with mmap.mmap(output.fileno(),0,access=mmap.ACCESS_READ) as view:
                return inspect(view,indirect,bounds,provenance,graph,disassembly,size)


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("apk",type=Path)
    a.add_argument("indirect_json",type=Path)
    a.add_argument("bounds_json",type=Path)
    a.add_argument("provenance_json",type=Path)
    a.add_argument("graph_json",type=Path)
    a.add_argument("llvm_disassembly",type=Path)
    a.add_argument("--function-size",type=int,required=True)
    a.add_argument("--output",type=Path,required=True)
    args=a.parse_args()
    obj=inspect_apk(args.apk,
        json.loads(args.indirect_json.read_text()),
        json.loads(args.bounds_json.read_text()),
        json.loads(args.provenance_json.read_text()),
        json.loads(args.graph_json.read_text()),
        args.llvm_disassembly.read_text(),args.function_size)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(obj,indent=2)+"\n")
    print(json.dumps({k:v for k,v in obj.items() if k!="sites"},indent=2))

if __name__=="__main__":main()
