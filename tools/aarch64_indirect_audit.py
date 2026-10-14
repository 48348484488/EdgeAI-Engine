#!/usr/bin/env python3
"""Conservative AArch64 indirect-jump *pattern* classification from LLVM disassembly.

Classifies ADR -> LDRSW indexed -> ADD -> BR shape when *consecutive*.
Does not read jump-table contents, resolve indirect destinations, execute code,
or infer gameplay/security semantics.
"""
import argparse
import json
import re
from pathlib import Path

INST = re.compile(r"^\s*([0-9a-fA-F]+):\s+([a-zA-Z][a-zA-Z0-9.]*)\b(.*?)\s*$")
REG = r"(x(?:[12]?\d|30))"
RE_ADD = re.compile(rf"^\s*{REG},\s*{REG},\s*{REG}\s*$")
RE_LDRSW = re.compile(rf"^\s*{REG},\s*\[{REG},\s*{REG},\s*lsl\s+#2\]\s*$")
RE_ADR = re.compile(rf"^\s*{REG},\s*0x[0-9a-fA-F]+(?:\s+.*)?$")
RE_BR = re.compile(rf"^\s*{REG}\s*$")


def parse_disassembly(text):
    instructions = {}
    for line in text.splitlines():
        m = INST.match(line)
        if not m:
            continue
        pc = int(m[1], 16)
        if pc in instructions:
            raise ValueError("duplicate LLVM address")
        instructions[pc] = (m[2].lower(), m[3].split("//", 1)[0].strip())
    return instructions


def analyze(scan, disassembly):
    if scan.get("architecture") != "AArch64" or scan.get("sample_truncated"):
        raise ValueError("complete AArch64 scan required")
    code = parse_disassembly(disassembly)
    entry = int(scan["entry"], 16)
    end = entry + scan["size_bytes"]
    events = scan["control_transfer_candidates"]
    sites = []
    for event in events:
        kind = event["kind"]
        if kind not in ("BR", "BLR"):
            continue
        pc = int(event["pc"], 16)
        if not entry <= pc < end or event["target"] is not None:
            raise ValueError("invalid indirect transfer")
        op, args = code.get(pc, ("", ""))
        if op.lower() != kind.lower():
            raise ValueError("LLVM/scanner mismatch at " + hex(pc))
        dest = RE_BR.fullmatch(args)
        if dest is None:
            raise ValueError("invalid indirect register operand")
        target_reg = dest[1]
        record = {
            "pc": hex(pc),
            "kind": kind,
            "target_register": target_reg,
            "target_resolved": False,
            "pattern": "unresolved_indirect_call" if kind == "BLR" else "unclassified_indirect_branch",
        }
        if kind == "BR":
            add = code.get(pc-4, ("", ""))
            load = code.get(pc-8, ("", ""))
            adr = code.get(pc-12, ("", ""))
            ad = RE_ADD.fullmatch(add[1]) if add[0] == "add" else None
            ld = RE_LDRSW.fullmatch(load[1]) if load[0] == "ldrsw" else None
            ar = RE_ADR.fullmatch(adr[1]) if adr[0] == "adr" else None
            if (ad and ld and ar and ad[1] == target_reg and
                    ad[2] == target_reg and ad[3] == ld[1] and
                    ar[1] == target_reg):
                record.update({
                    "pattern": "pc_relative_indexed_table_dispatch_candidate",
                    "evidence_pcs": [hex(pc-12), hex(pc-8), hex(pc-4), hex(pc)],
                    "index_register": ld[3],
                    "table_base_register": ld[2],
                    "relative_offset_register": ld[1],
                    "dispatch_base_register": target_reg,
                })
        sites.append(record)
    distribution = {}
    for s in sites:
        distribution[s["pattern"]] = distribution.get(s["pattern"], 0) + 1
    return {
        "function": scan["function"],
        "architecture": "AArch64",
        "entry": scan["entry"],
        "indirect_site_count": len(sites),
        "pattern_counts": distribution,
        "sites": sites,
        "code_executed": False,
        "jump_table_contents_read": False,
        "targets_resolved": False,
        "limitations": [
            "Exact consecutive ADR, LDRSW, ADD, BR syntax pattern only.",
            "A dispatch shape does not validate its index bounds or target addresses.",
            "No indirect targets or actual executed control paths are inferred.",
            "No gameplay state, player positions, camera, or original APK execution."
        ]
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("scan", type=Path)
    p.add_argument("llvm_disassembly", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = analyze(json.loads(args.scan.read_text()),
                     args.llvm_disassembly.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k:v for k,v in report.items() if k!="sites"}, indent=2))


if __name__ == "__main__":
    main()
