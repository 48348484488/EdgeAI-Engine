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
# LLVM may append a symbol annotation after an otherwise absolute target:
# "adrp x0, 0x33e000 <symbol+0xb0>". Accept only that exact suffix,
# never an arbitrary trailing operand that could be a register.
ADDRESS = re.compile(r"^#?(0x[0-9a-f]+|[0-9a-f]+)(?:\s+<[^>]+>)?$", re.I)
IMMEDIATE = re.compile(r"^#([+-]?(?:0x[0-9a-f]+|[0-9]+))$", re.I)
MEMORY = re.compile(r"\[\s*(x\d+)\s*(?:,\s*#([+-]?(?:0x[0-9a-f]+|[0-9]+)))?\s*\]", re.I)
MEMORY_BASE = re.compile(r"\[\s*(x\d+)\b", re.I)
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
            # A W-register write zero-extends/truncates the value. Never
            # propagate a 64-bit PC-relative address through Wn arithmetic.
            if args[0].lower().startswith("w") or args[1].lower().startswith("w"):
                tracked.pop(dest, None)
                continue
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
            if args[0].lower().startswith("w") or args[1].lower().startswith("w"):
                tracked.pop(dest, None)
                continue
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
            # Pre/post-indexed accesses modify the base even when we cannot
            # resolve their effective address. Keeping it would invent refs.
            base_match = MEMORY_BASE.search(operands)
            if base_match and ("!" in operands or re.search(r"\]\s*,", operands)):
                tracked.pop(_reg(base_match[1]), None)
            if op in LOADS and dest:
                tracked.pop(dest, None)
            continue
        if op in ("ldp", "ldpsw", "ldnp", "stp", "stnp"):
            # For simple, non-writeback pair accesses, both elements have
            # independently addressable locations. AArch64 W-register and
            # LDPSW pairs transfer 4-byte elements; X-register pairs use 8.
            # Reject SIMD registers and register-offset/writeback forms.
            writeback = "!" in operands or bool(re.search(r"\]\s*,", operands))
            pair_memory = MEMORY.search(operands)
            if (pair_memory and not writeback and operands.rstrip().endswith("]")
                    and len(args) >= 3
                    and all(re.fullmatch(r"[wx]\d+", a, re.I) for a in args[:2])):
                base = _reg(pair_memory[1])
                offset = _imm("#" + (pair_memory[2] or "0"))
                state = tracked.get(base)
                if state is not None and offset is not None:
                    width = 4 if op == "ldpsw" or args[0].lower().startswith("w") else 8
                    for index in range(2):
                        references.append({
                            "function": current, "pc": hex(pc),
                            "kind": "load" if op.startswith("ld") else "store",
                            "opcode": op,
                            "address": hex(state[0] + offset + index * width),
                            "origin_pc": hex(state[1]),
                            "pair_index": index, "width_bytes": width,
                        })
            # Pair loads overwrite both destinations, even if the base is
            # one of those destinations. Post/pre-index also clobbers base.
            if op.startswith("ld"):
                for item in args[:2]:
                    tracked.pop(_reg(item), None)
            base_match = MEMORY_BASE.search(operands)
            if base_match and writeback:
                tracked.pop(_reg(base_match[1]), None)
            continue
        if op.startswith(("b.", "cbz", "cbnz", "tbz", "tbnz")) or op in (
                "b", "bl", "blr", "br", "braa", "brab", "blraa", "blrab",
                "ret", "retaa", "retab", "svc", "eret"):
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
