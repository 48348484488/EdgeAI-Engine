#!/usr/bin/env python3
"""Prove supported play() outcomes from *executed control-flow paths*.

This is deliberately a narrow abstract interpreter for ARM32 play:
CMP r0,#imm with BHI/BLS and CMP of a verified board load with BEQ/BNE.
Unsupported operations never become evidence of acceptance or rejection.
"""
from collections import deque
import re

CMP = re.compile(r"^(r\d+),\s*#(0x[0-9a-fA-F]+|\d+)$")
TARGET = re.compile(r"^0x([0-9a-fA-F]+)")
BOARD_LOAD = re.compile(r"^(r\d+),\s*\[r2, r0, lsl #2\]$")
CONDITIONAL = {"bhi", "bls", "beq", "bne"}
MAX_UINT = 0xffffffff


def analyze(instructions, board_read_pcs, board_write_pcs, max_states=10000):
    """Explore supported paths. The board memory identity is an input proof."""
    nodes = {int(i["pc"], 16): i for i in instructions}
    if not nodes:
        return {"outcomes": [], "pruned": 0, "visited_states": 0}
    pcs = sorted(nodes)
    next_pc = {p: pcs[j + 1] for j, p in enumerate(pcs[:-1])}
    reads = {int(pc, 16) for pc in board_read_pcs}
    writes = {int(pc, 16) for pc in board_write_pcs}
    # State: pc, lo, hi (initial input r0), cell status, compare kind/value,
    # register holding board cell, board written, rejection marker.
    queue = deque([(pcs[0], 0, MAX_UINT, None, None, 0, None, False, False)])
    seen = set()
    outcomes = []
    pruned = 0
    unsupported = set()
    while queue:
        state = queue.popleft()
        if state in seen:
            continue
        seen.add(state)
        if len(seen) > max_states:
            raise ValueError("path-state budget exceeded")
        pc, lo, hi, cell, flags, immediate, cell_reg, written, minus_one = state
        if pc not in nodes:
            continue
        ins = nodes[pc]
        op, args = ins["mnemonic"].lower(), ins["operands"].strip()

        def add(dest, low=lo, high=hi, status=cell, cmp_kind=flags,
                cmp_value=immediate, loaded=cell_reg, stored=written, reject=minus_one):
            if dest in nodes:
                queue.append((dest, low, high, status, cmp_kind, cmp_value,
                              loaded, stored, reject))

        def finish(kind):
            outcomes.append({
                "event": kind,
                "pc": hex(pc),
                "input_position_unsigned": [lo, hi],
                "board_cell": "empty" if cell is True else "occupied" if cell is False else "unknown",
                "board_written": written
            })

        if op == "cmp":
            match = CMP.fullmatch(args)
            if match:
                reg, immediate_text = match.groups()
                immediate_value = int(immediate_text, 0)
                kind = "position" if reg == "r0" and not minus_one else (
                    "cell" if reg == cell_reg and immediate_value == 0 else None)
                add(next_pc.get(pc), cmp_kind=kind, cmp_value=immediate_value)
            else:
                add(next_pc.get(pc), cmp_kind=None)
        elif op in CONDITIONAL:
            target_match = TARGET.match(args)
            target = int(target_match[1], 16) if target_match else None
            for taken, dest in ((True, target), (False, next_pc.get(pc))):
                if dest is None:
                    continue
                new_lo, new_hi, new_cell = lo, hi, cell
                if flags == "position" and op in ("bhi", "bls"):
                    greater = (op == "bhi") == taken
                    if greater:
                        new_lo = max(lo, immediate + 1)
                    else:
                        new_hi = min(hi, immediate)
                elif flags == "cell" and op in ("beq", "bne"):
                    is_empty = (op == "beq") == taken
                    if cell is not None and cell != is_empty:
                        pruned += 1
                        continue
                    new_cell = is_empty
                if new_lo > new_hi:
                    pruned += 1
                    continue
                add(dest, low=new_lo, high=new_hi, status=new_cell, cmp_kind=None)
        elif op in ("ldr", "ldrb"):
            match = BOARD_LOAD.fullmatch(args)
            loaded = match[1] if match and pc in reads else None
            add(next_pc.get(pc), cmp_kind=None, loaded=loaded)
        elif op == "str":
            if pc not in writes:
                unsupported.add(hex(pc))
                finish("unverified_store")
            else:
                add(next_pc.get(pc), cmp_kind=None, stored=True)
        elif op == "mvn" and args == "r0, #0":
            add(next_pc.get(pc), cmp_kind=None, reject=True)
        elif op == "bx" and args == "lr":
            finish("return_minus_one" if minus_one else "return_unknown")
        elif op == "b":
            if "<winner>" in args and written:
                finish("winner_tail_jump")
            else:
                target_match = TARGET.match(args)
                target = int(target_match[1], 16) if target_match else None
                if target in nodes:
                    add(target, cmp_kind=None)
                else:
                    finish("other_external_branch")
        elif op in ("movw", "movt") and not args.startswith("r0,"):
            add(next_pc.get(pc), cmp_kind=None)
        else:
            unsupported.add(hex(pc))
            finish("unsupported_instruction")
    return {
        "outcomes": sorted(outcomes, key=lambda x: (x["event"], x["input_position_unsigned"], x["board_cell"])),
        "pruned": pruned,
        "visited_states": len(seen),
        "unsupported_pcs": sorted(unsupported),
        "scope": "Supported play-specific ARM path semantics; ranges describe initial unsigned R0, not all possible runtime states."
    }
