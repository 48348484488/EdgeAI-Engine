#!/usr/bin/env python3
"""Conservatively recover static ARM64 PC-relative data references.

Recognizes linked-ELF ADR/ADRP plus ADD and load/store addressing. This is
not pointer-value recovery, relocation resolution, or C++ decompilation.
Control-flow boundaries and unknown register writes invalidate assumptions.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

from edgeai_arm_callgraph import HEADER, INSTRUCTION, elf_architecture

REGISTER = re.compile(r"^[wx](\d+)$", re.I)
ADDRESS = re.compile(r"^#?(0x[0-9a-f]+|[0-9a-f]+)$", re.I)
IMMEDIATE = re.compile(r"^#([+-]?(?:0x[0-9a-f]+|[0-9]+))$", re.I)
MEMORY = re.compile(r"\[\s*(x\d+)\s*(?:,\s*#([+-]?(?:0x[0-9a-f]+|[0-9]+)))?\s*\]", re.I)
LOADS = {"ldr", "ldrb", "ldrh", "ldrsb", "ldrsh", "ldrsw", "ldur", "ldurb", "ldurh"}
STORES = {"str", "strb", "strh", "stur", "sturb", "sturh"}


def _reg(value):
    match = REGISTER.fullmatch(value.strip())
    return "x" + match[1] if match and int(match[1]) <= 30 else None


def _imm(value):
    match = IMMEDIATE.fullmatch(value.strip())
    if not match:
        return None
    token = match[1]
    return int(token, 16 if "0x" in token.lower() else 10)


def _absolute(value):
    match = ADDRESS.fullmatch(value.strip())
    return int(match[1], 16) if match else None


def analyze_text(disassembly):
    """Return candidate absolute addresses, not proven variable identities."""
    current = None
    tracked = {}
    references = []
    for line in disassembly.splitlines():
        header = HEADER.fullmatch(line)
        if header:
            current = header[2]
            tracked.clear()
            continue
        if current is None:
            continue
        parsed = INSTRUCTION.fullmatch(line)
        if not parsed:
            continue
        pc_text, op, operands = parsed.groups()
        pc = int(pc_text, 16)
        op = op.lower()
        args = [item.strip() for item in operands.split(",")]
        dest = _reg(args[0]) if args else None
        if op in ("adrp", "adr") and len(args) == 2 and dest:
            target = _absolute(args[1])
            if target is None:
                tracked.pop(dest, None)
            else:
                tracked[dest] = (target & ~0xfff if op == "adrp" else target, pc)
            continue
        if op == "add" and len(args) == 3 and dest:
            src, offset = _reg(args[1]), _imm(args[2])
            state = tracked.get(src)
            if state is not None and offset is not None:
                address = state[0] + offset
                tracked[dest] = (address, state[1])
                references.append({"function": current, "pc": hex(pc),
                                   "kind": "computed_address", "opcode": op,
                                   "address": hex(address), "origin_pc": hex(state[1])})
            else:
                tracked.pop(dest, None)
            continue
        if op == "mov" and len(args) == 2 and dest:
            src = _reg(args[1])
            if src in tracked:
                tracked[dest] = tracked[src]
            else:
                tracked.pop(dest, None)
            continue
        if op in LOADS | STORES:
            # Reject register-offset, pre/post-index and writeback forms.
            match = MEMORY.search(operands)
            if match and "!" not in operands and operands.rstrip().endswith("]"):
                base = _reg(match[1])
                offset = _imm("#" + (match[2] or "0"))
                state = tracked.get(base)
                if state is not None and offset is not None:
                    references.append({
                        "function": current, "pc": hex(pc),
                        "kind": "load" if op in LOADS else "store",
                        "opcode": op, "address": hex(state[0] + offset),
                        "origin_pc": hex(state[1]),
                    })
            if op in LOADS and dest:
                tracked.pop(dest, None)
            continue
        if op.startswith(("b.", "b", "cb", "tb")) or op in (
                "ret", "retaa", "retab", "br", "blr", "bl", "svc", "eret"):
            tracked.clear()
            continue
        # Conservatively invalidate the first register on any unmodeled
        # instruction that could overwrite it. Compare/store have no dest.
        if dest and op not in ("cmp", "cmn", "tst", "ccmp", "ccmn", "stp"):
            tracked.pop(dest, None)
    return {
        "architecture": "ARM64",
        "static_reference_count": len(references),
        "references": references,
        "limitations": [
            "Linked ARM64 executable/shared ELF only; relocatable objects are rejected",
            "Computed addresses are candidates, not proven variable or vtable identities",
            "Indirect addressing, register offsets, and control-flow merges are unresolved",
            "No source-level semantics, execution, or game fidelity established",
        ],
    }


def analyze_elf(path):
    path = Path(path)
    if elf_architecture(path) != "ARM64":
        raise ValueError("requires ARM64 ELF")
    header = path.read_bytes()[:20]
    elf_type = struct.unpack_from("<H", header, 16)[0]
    if elf_type not in (2, 3):
        raise ValueError("requires linked ARM64 executable or shared ELF")
    output = subprocess.run(
        ["llvm-objdump", "--no-show-raw-insn", "-d", str(path)],
        capture_output=True, text=True, check=True, timeout=90,
    ).stdout
    return analyze_text(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = analyze_elf(args.elf)
    payload = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
