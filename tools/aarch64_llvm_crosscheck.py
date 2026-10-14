#!/usr/bin/env python3
"""Fail-closed comparison of AArch64 static control transfers AND direct targets with LLVM.

This cross-check verifies opcode category, PC and PC-relative branch/call
destination as independently printed by llvm-objdump. It is not execution,
feasibility or function semantics proof.
"""
import argparse
import json
import re
from pathlib import Path

LINE = re.compile(r"^\s*([0-9a-fA-F]+):\s+([a-zA-Z][a-zA-Z0-9.]*)\b(.*?)$")
HEX = re.compile(r"0x[0-9a-fA-F]+\b")
SIMPLE = {"b": "B", "bl": "BL", "br": "BR", "blr": "BLR",
          "ret": "RET", "cbz": "CBZ", "cbnz": "CBNZ",
          "tbz": "TBZ", "tbnz": "TBNZ"}
DIRECT = frozenset(("B", "BL", "B.cond", "CBZ", "CBNZ", "TBZ", "TBNZ"))


def llvm_transfers(raw):
    result = {}
    for line in raw.splitlines():
        match = LINE.match(line)
        if match is None:
            continue
        pc = int(match[1], 16)
        opname = match[2].lower()
        kind = SIMPLE.get(opname)
        if kind is None and opname.startswith("b.") and opname != "b.al":
            kind = "B.cond"
        if kind is None:
            continue
        operand_text = match[3].split("<", 1)[0].strip()
        if kind in DIRECT:
            # AArch64 TBZ/TBNZ has a separate bit-number operand; the
            # final hexadecimal argument is the branch destination.
            destinations = HEX.findall(operand_text)
            if not destinations:
                raise ValueError("LLVM omitted direct target at " + hex(pc))
            target = int(destinations[-1], 16)
        else:
            target = None
        if pc in result:
            raise ValueError("duplicate LLVM control instruction")
        result[pc] = {"kind": kind, "target": target}
    return result


def compare(scan, llvm):
    if scan.get("architecture") != "AArch64" or scan.get("sample_truncated"):
        raise ValueError("requires full AArch64 function scan")
    start = int(scan["entry"], 16)
    size = scan["size_bytes"]
    if size < 4 or size % 4 or start % 4:
        raise ValueError("bad symbol bounds")
    end = start + size
    recorded = scan["control_transfer_candidates"]
    if len(recorded) != scan["decoded_control_transfers"]:
        raise ValueError("incomplete scanner data")
    ours = {}
    for record in recorded:
        pc = int(record["pc"], 16)
        kind = record["kind"]
        if pc in ours or pc < start or pc >= end or pc % 4:
            raise ValueError("bad scanner PC")
        if kind not in DIRECT and kind not in ("BR", "BLR", "RET"):
            raise ValueError("unknown scanner opcode class")
        target_value = record["target"]
        if kind in DIRECT:
            if target_value is None:
                raise ValueError("missing scanner direct destination")
            target = int(target_value, 16)
            if target % 4 or target < 0:
                raise ValueError("invalid scanner direct destination")
        else:
            if target_value is not None:
                raise ValueError("unexpected target for indirect/return")
            target = None
        ours[pc] = {"kind": kind, "target": target}
    theirs = llvm_transfers(llvm)
    if any(pc < start or pc >= end or pc % 4 for pc in theirs):
        raise ValueError("LLVM disassembly includes instructions outside selected function")
    opcode_matches = []
    exact_matches = []
    mismatches = []
    direct_checked = 0
    target_matches = 0
    for pc in sorted(set(ours) | set(theirs)):
        expected, actual = ours.get(pc), theirs.get(pc)
        if expected is not None and actual is not None and expected["kind"] == actual["kind"]:
            opcode_matches.append(pc)
            if expected["kind"] in DIRECT:
                direct_checked += 1
                if expected["target"] == actual["target"]:
                    target_matches += 1
            if expected["target"] == actual["target"]:
                exact_matches.append(pc)
                continue
        mismatches.append({
            "pc": hex(pc),
            "scanner": None if expected is None else {
                "kind": expected["kind"],
                "target": None if expected["target"] is None else hex(expected["target"]),
            },
            "llvm": None if actual is None else {
                "kind": actual["kind"],
                "target": None if actual["target"] is None else hex(actual["target"]),
            },
        })
    return {
        "architecture": "AArch64", "function": scan["function"], "entry": scan["entry"],
        "function_size_bytes": size,
        "scanner_controls": len(ours), "llvm_controls": len(theirs),
        "opcode_agreements": len(opcode_matches),
        "direct_target_comparisons": direct_checked,
        "direct_target_agreements": target_matches,
        "exact_agreements": len(exact_matches),
        "mismatches": mismatches[:100], "total_mismatches": len(mismatches),
        "status": "MATCH" if not mismatches else "MISMATCH",
        "original_code_executed": False,
        "source": "LLVM objdump static AArch64 disassembly",
        "scope": "Address, control opcode class, and direct branch destination only; no semantic/reachability proof",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("edgeai_json", type=Path)
    p.add_argument("llvm_disassembly", type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    report = compare(json.loads(a.edgeai_json.read_text()), a.llvm_disassembly.read_text())
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["status"] != "MATCH":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
