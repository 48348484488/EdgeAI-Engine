#!/usr/bin/env python3
"""Conservative ARM32/ARM64 ELF call graph audit from llvm-objdump.

This is a generic *static* discovery aid for reverse engineering. It does not
decompile functions or prove runtime behavior. Indirect calls remain unresolved.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

HEADER = re.compile(r"^\s*([0-9a-fA-F]+) <([^>]+)>:\s*$")
INSTRUCTION = re.compile(
    r"^\s*([0-9a-fA-F]+):\s+"
    r"(?:(?:[0-9a-fA-F]{2}(?:\s+[0-9a-fA-F]{2}){1,3}|"
    r"[0-9a-fA-F]{4}(?:\s+[0-9a-fA-F]{4})?|"
    r"[0-9a-fA-F]{8})\s+)?"
    r"([a-zA-Z][a-zA-Z0-9.]*)\s*(.*?)\s*$"
)
DIRECT = re.compile(r"^0x([0-9a-fA-F]+)(?:\s|$)")


def elf_architecture(path):
    data = Path(path).read_bytes()[:20]
    if len(data) < 20 or data[:4] != b"\x7fELF" or data[5] != 1:
        raise ValueError("requires little-endian ELF")
    machine = struct.unpack_from("<H", data, 18)[0]
    if (data[4], machine) == (1, 40):
        return "ARM32"
    if (data[4], machine) == (2, 183):
        return "ARM64"
    raise ValueError("requires ARM32 or ARM64 ELF")


def analyze_text(disassembly, architecture):
    """Parse function entry labels, direct calls, unresolved calls and tail edges.

    The input is disassembly, not a source listing. Branches to an address
    inside the same function are *not* reported as interprocedural edges.
    """
    if architecture not in ("ARM32", "ARM64"):
        raise ValueError("unsupported architecture")
    functions = []
    current = None
    for raw in disassembly.splitlines():
        header = HEADER.fullmatch(raw)
        if header:
            current = {
                "name": header[2], "address": int(header[1], 16),
                "instructions": [],
            }
            functions.append(current)
            continue
        if current is None:
            continue
        match = INSTRUCTION.fullmatch(raw)
        if match:
            pc, op, operands = match.groups()
            current["instructions"].append(
                (int(pc, 16), op.lower(), operands.split("@", 1)[0].strip())
            )
    if not functions:
        raise ValueError("no labeled functions in disassembly")
    addresses = {f["address"]: f["name"] for f in functions}
    if len(addresses) != len(functions):
        raise ValueError("duplicate function entry address")

    result = []
    all_calls = []
    indirect = []
    tails = []
    for index, func in enumerate(functions):
        next_address = functions[index + 1]["address"] if index + 1 < len(functions) else None
        calls = []
        for pc, op, operands in func["instructions"]:
            is_call = op in (("bl", "blx") if architecture == "ARM32" else ("bl", "blr"))
            is_unconditional_tail = op in (("b", "bx") if architecture == "ARM32" else ("b", "br"))
            if not (is_call or is_unconditional_tail):
                continue
            match = DIRECT.match(operands)
            target = int(match[1], 16) if match else None
            if is_call:
                item = {
                    "pc": hex(pc), "opcode": op,
                    "target": hex(target) if target is not None else None,
                    "target_function": addresses.get(target) if target is not None else None,
                    "indirect": target is None,
                }
                calls.append(item)
                all_calls.append({"from": func["name"], **item})
                if target is None:
                    indirect.append({"from": func["name"], **item})
            elif target is not None and target in addresses and target != func["address"]:
                # Only label-backed cross-function unconditional branches are
                # claimed as tail edges; local loop/condition branches excluded.
                tails.append({
                    "from": func["name"], "pc": hex(pc),
                    "to": addresses[target], "target": hex(target)
                })
        result.append({
            "name": func["name"], "address": hex(func["address"]),
            "instruction_count": len(func["instructions"]),
            "direct_call_count": sum(not c["indirect"] for c in calls),
            "indirect_call_count": sum(c["indirect"] for c in calls),
        })
    return {
        "architecture": architecture, "function_count": len(result),
        "functions": result, "calls": all_calls,
        "indirect_calls": indirect, "tail_edges": tails,
        "unresolved_direct_targets": sorted({
            c["target"] for c in all_calls
            if c["target"] is not None and c["target_function"] is None
        }),
        "limitations": [
            "Static call sites only; indirect targets unresolved",
            "Function boundaries require objdump labels; stripped or unlabeled code may be missed",
            "No proof of source-level semantics, execution, or game fidelity",
        ],
    }


def analyze_elf(path):
    architecture = elf_architecture(path)
    output = subprocess.run(
        ["llvm-objdump", "--no-show-raw-insn", "-d", str(path)],
        capture_output=True, text=True, check=True, timeout=90,
    ).stdout
    return analyze_text(output, architecture)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = analyze_elf(args.elf)
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
