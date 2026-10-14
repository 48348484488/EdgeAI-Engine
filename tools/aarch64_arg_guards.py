#!/usr/bin/env python3
"""Bounded AArch64 argument guard candidates from original LLVM disassembly.

Track entry argument copied to an AAPCS64-preserved W/X19..28 register,
then CMP #immediate + B.EQ/B.NE. This is a LINEAR candidate, not full
dataflow, path proof, gameplay semantics, or C++ reconstruction.
"""
import argparse
import json
import re
from pathlib import Path
from aarch64_indirect_audit import parse_disassembly

MOV=re.compile(r"^(w|x)(\d{1,2}),\s*\1(\d{1,2})$")
CMP=re.compile(r"^(w|x)(\d{1,2}),\s*#(0x[0-9a-fA-F]+|\d+)$")
DEST=re.compile(r"^(?:w|x)(\d{1,2})(?:,|$)")
PAIR=re.compile(r"^(?:w|x)(\d{1,2}),\s*(?:w|x)(\d{1,2}),")
NO_WRITE=set(("cmp","cmn","tst","b","b.eq","b.ne","b.hi","b.hs","b.lo",
"b.ls","b.gt","b.ge","b.lt","b.le","b.mi","b.pl","b.vs","b.vc",
"cbz","cbnz","tbz","tbnz","ret","br","nop","hint","dmb","dsb","isb"))
STORE=set(("str","strb","strh","stur","sturb","sturh","stp","stnp"))
TWO=set(("ldp","ldnp","ldpsw"))
ONE=set(("mov","movz","movn","movk","add","adds","sub","subs",
"mul","madd","msub","ldr","ldrb","ldrh","ldrsb","ldrsh","ldrsw",
"ldur","ldurb","ldurh","ldar","ldarb","ldaxr","ldxr","adr","adrp",
"csel","csinc","csinv","csneg","orr","orn","and","ands","eor","eon",
"lsl","lsr","asr","ubfx","sbfm","ubfm","uxtw","sxtw"))

def tracked_write(op,args,reg):
    """True/False/None: overwrites/preserves/unknown effect."""
    if op in ("bl","blr"):
        return False  # AAPCS64: x19-x28 preserved by callees (assumption).
    if op in NO_WRITE:
        return False
    if op in STORE:
        return None if "!" in args or "]," in args else False
    if op in TWO:
        m=PAIR.match(args)
        return reg in (int(m[1]),int(m[2])) if m else None
    if op in ONE:
        m=DEST.match(args)
        return int(m[1])==reg if m else None
    return None

def infer(scan,llvm_text):
    if scan.get("architecture")!="AArch64" or scan.get("sample_truncated"):
        raise ValueError("requires complete AArch64 control-transfer scan")
    entry=int(scan["entry"],16)
    size=scan["size_bytes"]
    if entry%4 or size<=0 or size>1024*1024 or size%4:
        raise ValueError("invalid known ELF function bounds")
    end=entry+size
    code=parse_disassembly(llvm_text)
    if not code or any(pc<entry or pc>=end or pc%4 for pc in code):
        raise ValueError("LLVM listing outside selected function")
    transfers=scan["control_transfer_candidates"]
    if len(transfers)!=scan["decoded_control_transfers"]:
        raise ValueError("truncated control-transfer evidence")
    events={}
    for event in transfers:
        pc=int(event["pc"],16)
        if pc in events or not entry<=pc<end or pc%4:
            raise ValueError("invalid control-transfer address")
        events[pc]=event
    copies=[]
    for pc,(op,args) in sorted(code.items()):
        m=MOV.fullmatch(args) if op=="mov" else None
        if m:
            width,dest,src=m[1],int(m[2]),int(m[3])
            if 19<=dest<=28 and 0<=src<=7:
                copies.append((pc,width,dest,src))
    candidates,rejected=[],[]
    for pc,(op,args) in sorted(code.items()):
        m=CMP.fullmatch(args) if op=="cmp" else None
        if m is None:continue
        width,reg,value=m[1],int(m[2]),m[3]
        following=code.get(pc+4)
        if following is None or following[0] not in ("b.eq","b.ne"):
            continue
        branch=events.get(pc+4)
        if branch is None or branch["kind"]!="B.cond" or branch["target"] is None:
            raise ValueError("LLVM branch and binary scanner disagree")
        recent=[a for a in copies if a[0]<pc and a[1]==width and a[2]==reg]
        if not recent:continue
        copied_at,_,_,arg=max(recent)
        reason=None
        for address in range(copied_at+4,pc,4):
            ins=code.get(address)
            if ins is None:
                reason="instruction_gap";break
            changed=tracked_write(ins[0],ins[1],reg)
            if changed is None:
                reason="unknown_register_effect";break
            if changed:
                reason="register_overwritten";break
            if ins[0] in ("b","br","ret"):
                reason="linear_control_flow_interrupted";break
        if reason is None:
            for ev in transfers:
                target=ev.get("target")
                if target is not None and copied_at<int(target,16)<=pc:
                    reason="branch_enters_tracked_interval";break
        if reason is not None:
            rejected.append({"compare_pc":hex(pc),"copy_pc":hex(copied_at),"reason":reason})
            continue
        candidates.append({
            "copy_pc":hex(copied_at),"compare_pc":hex(pc),
            "conditional_branch_pc":hex(pc+4),"branch_target":branch["target"],
            "argument_index":arg,"argument_width_bits":32 if width=="w" else 64,
            "saved_register":width+str(reg),"compared_immediate":int(value,0),
            "branch_if_argument":"not_equal" if following[0]=="b.ne" else "equal",
            "evidence":"bounded_linear_copy_compare_with_AAPCS64_preservation_assumption",
            "all_incoming_paths_proven":False,"original_code_executed":False})
    return {
        "architecture":"AArch64","function":scan["function"],"entry":scan["entry"],
        "candidate_count":len(candidates),"rejected_count":len(rejected),
        "candidates":candidates,"rejected":rejected,
        "original_code_executed":False,"global_path_feasibility_proven":False,
        "assumptions":["AAPCS64 callees preserve x19-x28",
                       "Selected ELF symbol bounds and a 4-byte-aligned LLVM listing"],
        "limitations":["Linear register-copy candidates; no full CFG/dataflow/path proof.",
                      "Unknown writes and any direct branch into the tracked interval are rejected.",
                      "An immediate comparison alone does not identify parameter meaning.",
                      "No game execution, recovered player positions, camera, or C++ source."]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("scan_json",type=Path)
    p.add_argument("llvm_disassembly",type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    result=infer(json.loads(a.scan_json.read_text()),a.llvm_disassembly.read_text())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
