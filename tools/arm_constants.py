#!/usr/bin/env python3
"""Conservative ARM32 constant propagation for straight-line instructions."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

path = Path(__file__).with_name("arm_semantics.py")
spec = importlib.util.spec_from_file_location("edgeai_semantics", path)
sem = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sem)


def propagate(data, entry, max_steps=256):
    if entry % 4 or not 1 <= max_steps <= 4096:
        raise sem.cfg.arm.ScanError("invalid ARM entry or step limit")
    order, segments = sem.cfg.arm.exec_segments(data)
    registers = {}
    trace = []
    pc = entry
    for _ in range(max_steps):
        offset = next((off + pc - base for off, base, size in segments
                       if base <= pc and pc + 4 <= base + size), None)
        if offset is None:
            break
        word = struct.unpack_from(order + "I", data, offset)[0]
        decoded = sem.decode_arm(word, pc)
        operation = decoded["operation"]
        if decoded["condition"] != "al":
            trace.append({"pc": hex(pc), "status": "stopped_at_condition"})
            break
        if operation == "MOV":
            registers[decoded["destination"]] = decoded["immediate"]
        elif operation in ("ADD", "SUB"):
            previous = registers.get(decoded["source"])
            value = None if previous is None else (
                previous + decoded["immediate"] if operation == "ADD"
                else previous - decoded["immediate"]) & 0xffffffff
            registers[decoded["destination"]] = value
        elif operation == "CMP":
            previous = registers.get(decoded["source"])
            trace.append({"pc": hex(pc), "operation": "CMP",
                          "equal": None if previous is None
                          else previous == decoded["immediate"]})
            pc += 4
            continue
        else:
            trace.append({"pc": hex(pc), "status": "stopped_at_unknown_or_control",
                          "operation": operation})
            break
        trace.append({"pc": hex(pc), "operation": operation,
                      "known_registers": {k: hex(v) for k, v in registers.items()
                                          if v is not None}})
        pc += 4
    return {"entry": hex(entry), "trace": trace,
            "known_registers": {k: hex(v) for k, v in registers.items()
                                if v is not None},
            "limitations": "Straight-line ARM immediate operations only; no memory or branch merges."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("elf", type=Path)
    parser.add_argument("--entry", required=True, type=lambda s: int(s, 0))
    args = parser.parse_args()
    try:
        if args.elf.stat().st_size > 128 * 1024 * 1024:
            raise sem.cfg.arm.ScanError("file too large")
        output = propagate(args.elf.read_bytes(), args.entry)
    except (OSError, sem.cfg.arm.ScanError, struct.error) as error:
        parser.exit(2, f"error: {error}\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
