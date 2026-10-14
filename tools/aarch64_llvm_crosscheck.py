#!/usr/bin/env python3
"""Fail-closed comparison of an AArch64 symbol scan with LLVM disassembly."""
import argparse
import json
import re
from pathlib import Path

LINE = re.compile(r"^\s*([0-9a-fA-F]+):\s+([a-zA-Z][a-zA-Z0-9.]*)\b")
SIMPLE = {"b": "B", "bl": "BL", "br": "BR", "blr": "BLR",
          "ret": "RET", "cbz": "CBZ", "cbnz": "CBNZ",
          "tbz": "TBZ", "tbnz": "TBNZ"}


def llvm_transfers(raw):
    result = {}
    for line in raw.splitlines():
        m = LINE.match(line)
        if m is None: continue
        pc = int(m[1], 16)
        opname = m[2].lower()
        kind = SIMPLE.get(opname)
        if kind is None and opname.startswith("b.") and opname != "b.al":
            kind = "B.cond"
        if kind is None: continue
        if pc in result: raise ValueError("duplicate LLVM control instruction")
        result[pc] = kind
    return result


def compare(scan, llvm):
    if scan.get("architecture")!="AArch64" or scan.get("sample_truncated"):
        raise ValueError("requires full AArch64 function scan")
    start=int(scan["entry"],16)
    end=start+scan["size_bytes"]
    recorded=scan["control_transfer_candidates"]
    if len(recorded)!=scan["decoded_control_transfers"]:
        raise ValueError("incomplete scanner data")
    ours={}
    for record in recorded:
        pc=int(record["pc"],16)
        if pc in ours or pc<start or pc>=end or pc%4:
            raise ValueError("bad scanner PC")
        ours[pc]=record["kind"]
    theirs=llvm_transfers(llvm)
    if any(pc<start or pc>=end or pc%4 for pc in theirs):
        raise ValueError("LLVM disassembly includes instructions outside selected function")
    matched=sorted(pc for pc in ours if theirs.get(pc)==ours[pc])
    mismatches=[]
    for pc in sorted(set(ours)|set(theirs)):
        if ours.get(pc)!=theirs.get(pc):
            mismatches.append({"pc":hex(pc),"scanner":ours.get(pc),"llvm":theirs.get(pc)})
    return {
        "architecture":"AArch64", "function":scan["function"], "entry":scan["entry"],
        "function_size_bytes":scan["size_bytes"],
        "scanner_controls":len(ours), "llvm_controls":len(theirs),
        "exact_agreements":len(matched),
        "mismatches":mismatches[:100], "total_mismatches":len(mismatches),
        "status":"MATCH" if not mismatches else "MISMATCH",
        "original_code_executed":False,
        "source":"LLVM objdump read-only disassembly, independent of EdgeAI opcode decoder",
        "scope":"Address and opcode-class agreement only; semantics or reachability not proven"
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("edgeai_json",type=Path)
    p.add_argument("llvm_disassembly",type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    report=compare(json.loads(a.edgeai_json.read_text()),a.llvm_disassembly.read_text())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    if report["status"]!="MATCH":raise SystemExit(1)


if __name__=="__main__":main()
