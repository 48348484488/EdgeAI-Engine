#!/usr/bin/env python3
"""Fail-closed, source-blind AArch64 control-flow graph extraction.

This tool reconstructs *control flow only* from disassembly. It does not lift
instructions into C++, infer ABI contracts, or claim behavior equivalence.
"""
import argparse
import hashlib
import json
import re
import subprocess
from collections import deque
from pathlib import Path

INSTRUCTION = re.compile(r'^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F]{8}\s+([\w.]+)(?:\s+(.*))?$')
TARGET = re.compile(r'^0x([0-9a-fA-F]+)(?:\s|$)')
GUARD = re.compile(r'^([wx]\d+),\s*#(0x[0-9a-fA-F]+|\d+)(?:\s|$)')
BRANCH_COND = {'cbz', 'cbnz', 'tbz', 'tbnz'}
RETURN = {'ret', 'eret', 'retaa', 'retab'}
INDIRECT = {'br', 'braa', 'brab'}


def parse_instructions(data):
    rows = []
    for line in data.splitlines():
        match = INSTRUCTION.match(line)
        if match:
            address, mnemonic, operands = match.groups()
            rows.append((int(address, 16), mnemonic.lower(), (operands or '').split(' //')[0].strip()))
    return rows


def branch_target(op, operands):
    if op in {'b', 'bl'} or op.startswith('b.'):
        arg = operands
    elif op in BRANCH_COND:
        arg = operands.rsplit(',', 1)[-1].strip()
    else:
        return None
    match = TARGET.match(arg)
    return int(match.group(1), 16) if match else None


def build_cfg(rows, start, end):
    if start >= end or start % 4 or end % 4:
        raise ValueError('invalid aligned function range')
    selected = [(pc, op, args) for pc, op, args in rows if start <= pc < end]
    instructions = {pc: (op, args) for pc, op, args in selected}
    if len(selected) != len(instructions):
        raise ValueError('duplicate instruction addresses in function range')
    expected = set(range(start, end, 4))
    if set(instructions) != expected:
        raise ValueError('incomplete or duplicate disassembly in function range')
    successors = {}
    calls = []
    guards = []
    indirect = []
    for pc in sorted(instructions):
        op, args = instructions[pc]
        nxt = pc + 4
        target = branch_target(op, args)
        is_cond = op.startswith('b.') or op in BRANCH_COND
        if op in {'bl', 'blr'}:
            calls.append({'pc': hex(pc), 'target': hex(target) if target is not None else None,
                          'symbol': args.split('<', 1)[-1].split('>', 1)[0] if '<' in args else None,
                          'indirect': op == 'blr'})
        if op in RETURN:
            destinations = []
        elif op in INDIRECT:
            indirect.append(hex(pc))
            destinations = []
        elif op == 'b':
            if target is None:
                raise ValueError(f'unknown direct branch target at {pc:#x}')
            destinations = [target]
        elif is_cond:
            if target is None:
                raise ValueError(f'unknown conditional branch target at {pc:#x}')
            destinations = [target, nxt]
            prev = instructions.get(pc - 4)
            guard = {'pc': hex(pc), 'mnemonic': op, 'target': hex(target)}
            if prev and prev[0] in {'cmp', 'cmn'}:
                m = GUARD.match(prev[1])
                if m:
                    guard['adjacent_compare'] = {'op': prev[0], 'register': m.group(1),
                                                 'immediate': int(m.group(2), 0)}
            guards.append(guard)
        else:
            destinations = [nxt]
        for dest in destinations:
            if start <= dest < end and dest not in instructions:
                raise ValueError(f'branch to missing instruction {dest:#x}')
        successors[pc] = destinations
    leaders = {start}
    for pc, (op, _) in instructions.items():
        destinations = successors[pc]
        if op == 'b' or op.startswith('b.') or op in BRANCH_COND or op in RETURN or op in INDIRECT:
            leaders.update(d for d in destinations if d in instructions)
            if pc + 4 in instructions:
                leaders.add(pc + 4)
    ordered = sorted(leaders)
    blocks = []
    for i, leader in enumerate(ordered):
        stop = ordered[i + 1] if i + 1 < len(ordered) else end
        pcs = list(range(leader, stop, 4))
        last = pcs[-1]
        blocks.append({'start': hex(leader), 'end_exclusive': hex(stop),
                       'instructions': len(pcs), 'last_mnemonic': instructions[last][0],
                       'successors': [hex(x) for x in successors[last] if start <= x < end],
                       'external_successors': [hex(x) for x in successors[last] if not start <= x < end]})
    block_by_pc = {}
    for block in blocks:
        for pc in range(int(block['start'], 16), int(block['end_exclusive'], 16), 4):
            block_by_pc[pc] = int(block['start'], 16)
    reachable = {start}
    queue = deque([start])
    while queue:
        pc = queue.popleft()
        block = next(b for b in blocks if int(b['start'], 16) == pc)
        for addr in block['successors']:
            target_block = block_by_pc[int(addr, 16)]
            if target_block not in reachable:
                reachable.add(target_block)
                queue.append(target_block)
    edges = [(int(b['start'], 16), int(t, 16)) for b in blocks for t in b['successors']]
    simd_memory = [hex(pc) for pc, (op, args) in instructions.items()
                   if op in {'ldp', 'stp', 'ldr', 'str', 'ldur', 'stur'} and
                   re.search(r'\b[qdsv]\d+\b', args)]
    return {'start': hex(start), 'end_exclusive': hex(end), 'instruction_count': len(instructions),
            'block_count': len(blocks), 'reachable_blocks': len(reachable),
            'unreachable_blocks': [hex(int(b['start'], 16)) for b in blocks if int(b['start'], 16) not in reachable],
            'backward_edges': [{'from': hex(src), 'to': hex(dst)} for src, dst in edges if dst <= src],
            'conditional_guards': guards, 'calls': calls, 'simd_memory_instructions': simd_memory,
            'indirect_branches': indirect, 'blocks': blocks,
            'limitations': 'Static CFG only; external calls, indirect edges, exceptions, memory semantics and ABI are not modeled. Backward edges are not proof of loop execution.'}


def analyze_elf(elf, start, end, expected_sha256=None):
    digest = hashlib.sha256(elf.read_bytes()).hexdigest()
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        raise ValueError('ELF SHA-256 mismatch; refusing to analyze different binary')
    disasm = subprocess.run(['llvm-objdump', '-d', str(elf)], check=True,
                            capture_output=True, text=True).stdout
    result = build_cfg(parse_instructions(disasm), start, end)
    result['binary_sha256'] = digest
    result['source_read'] = False
    result['behaviorally_validated'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', required=True, type=Path)
    parser.add_argument('--start', required=True, type=lambda x: int(x, 0))
    parser.add_argument('--end', required=True, type=lambda x: int(x, 0))
    parser.add_argument('--expected-sha256')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = analyze_elf(args.elf, args.start, args.end, args.expected_sha256)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['instruction_count']} instructions; {result['block_count']} basic blocks; "
          f"{result['reachable_blocks']} reachable; {len(result['calls'])} calls; no C++ emitted")


if __name__ == '__main__':
    main()
