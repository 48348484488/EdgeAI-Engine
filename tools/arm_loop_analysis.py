#!/usr/bin/env python3
"""Bounded ARM disassembly CFG, natural-loop and memory-access evidence.

Function-name independent. Natural loops require a dominance-proven
back edge; irregular/indirect control flow is reported as incomplete.
Does not infer original C++ loop bodies or prove register values.
"""
import argparse
from collections import defaultdict, deque
import json
from pathlib import Path
import re
import subprocess

BRANCHES = {'beq', 'bne', 'bhi', 'bls', 'bcs', 'bcc', 'bge', 'blt',
            'bgt', 'ble', 'bmi', 'bpl', 'bvs', 'bvc'}
TARGET = re.compile(r'^0x([0-9a-fA-F]+)(?:\s|$)')
HEADER = re.compile(r'^([0-9a-fA-F]+) <([^>]+)>:$')
INSTRUCTION = re.compile(r'^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F]{8}\s+([a-zA-Z][a-zA-Z0-9.]*)\s*(.*?)\s*$')
MEMORY = re.compile(r'^([^,]+),\s*\[([^,\]]+)(?:,\s*([^\]]+))?\](!)?(?:,\s*(#-?(?:0x[0-9a-fA-F]+|\d+)))?$')
IMM = re.compile(r'^(r\d+),\s*#(0x[0-9a-fA-F]+|\d+)$')


def disassemble_function(text, function):
    """Parse a selected LLVM-disassembled function, never guessing its end."""
    lines = text.splitlines()
    in_function = False
    output = []
    for line in lines:
        header = HEADER.fullmatch(line.strip())
        if header:
            if in_function:
                break
            in_function = header[2] == function
            continue
        if in_function:
            item = INSTRUCTION.match(line)
            if item:
                pc, op, args = item.groups()
                output.append({'pc': hex(int(pc, 16)), 'mnemonic': op.lower(),
                               'operands': args.split('@')[0].strip()})
    if not output:
        raise ValueError('function was not found or had no disassembly: ' + function)
    return output


def analyze(instructions, function=None, max_instructions=20000):
    if not instructions or len(instructions) > max_instructions:
        raise ValueError('empty function or instruction budget exceeded')
    normalized = []
    for row in instructions:
        pc = int(row['pc'], 16) if isinstance(row['pc'], str) else row['pc']
        op = row.get('mnemonic', row.get('op'))
        args = row.get('operands', row.get('args', ''))
        if not isinstance(pc, int) or pc < 0 or pc > 0xffffffff or not isinstance(op, str):
            raise ValueError('invalid ARM instruction')
        normalized.append((pc, op.lower(), args.strip()))
    normalized.sort()
    pcs = [pc for pc, _, _ in normalized]
    if len(set(pcs)) != len(pcs):
        raise ValueError('duplicate instruction address')
    by_pc = {pc: (op, args) for pc, op, args in normalized}
    next_pc = {pc: pcs[i + 1] for i, pc in enumerate(pcs[:-1])}
    successors = defaultdict(set)
    external_edges = []
    unknown_control = []
    conditional_returns = []
    for pc, op, args in normalized:
        predicated_bx = re.fullmatch(r'bx(eq|ne|hi|ls|cs|cc|ge|lt|gt|le|mi|pl|vs|vc)', op)
        if predicated_bx:
            # The taken path exits; the false path falls through.
            conditional_returns.append({'pc': hex(pc), 'condition': predicated_bx[1], 'register': args})
            if args not in ('lr', 'r14'):
                unknown_control.append(hex(pc))
            if pc in next_pc:
                successors[pc].add(next_pc[pc])
            continue
        is_ret = (op == 'bx') or (op == 'pop' and re.search(r'\bpc\b', args) is not None)
        if is_ret:
            if op == 'bx' and args not in ('lr', 'r14'):
                unknown_control.append(hex(pc))
            continue
        if op == 'b' or op in BRANCHES:
            match = TARGET.match(args)
            if not match:
                unknown_control.append(hex(pc))
                continue
            target = int(match[1], 16)
            if target in by_pc:
                successors[pc].add(target)
            else:
                external_edges.append({'from': hex(pc), 'to': hex(target), 'type': 'external_branch'})
            if op in BRANCHES and pc in next_pc:
                successors[pc].add(next_pc[pc])
        elif op in ('bl', 'blx'):
            if pc in next_pc:
                successors[pc].add(next_pc[pc])
        elif op.startswith('b') and op not in ('bic', 'bics', 'bkpt'):
            unknown_control.append(hex(pc))
        elif pc in next_pc:
            successors[pc].add(next_pc[pc])
    entry = pcs[0]
    reachable = set()
    queue = deque([entry])
    while queue:
        pc = queue.popleft()
        if pc in reachable:
            continue
        reachable.add(pc)
        queue.extend(successors[pc] - reachable)
    predecessors = defaultdict(set)
    for pc in reachable:
        for dst in successors[pc]:
            if dst in reachable:
                predecessors[dst].add(pc)
    # Integer bitsets avoid allocating O(V^2) Python-set elements on large
    # graphs and make dominator intersections efficient on modest CPUs.
    order = sorted(reachable)
    bits = {pc: 1 << i for i, pc in enumerate(order)}
    all_bits = (1 << len(order)) - 1
    dominators = {pc: (bits[pc] if pc == entry else all_bits) for pc in order}
    changed = True
    while changed:
        changed = False
        for pc in order:
            if pc == entry:
                continue
            incoming = predecessors[pc]
            shared = all_bits
            for pred in incoming:
                shared &= dominators[pred]
            new = bits[pc] | (shared if incoming else 0)
            if new != dominators[pc]:
                dominators[pc] = new
                changed = True
    back_edges = [(src, dst) for src in order for dst in sorted(successors[src])
                  if dst in bits and dominators[src] & bits[dst]]
    loops = defaultdict(lambda: {'latches': set(), 'nodes': set()})
    for latch, header in back_edges:
        nodes = {header, latch}
        pending = [latch] if latch != header else []
        while pending:
            current = pending.pop()
            for pred in predecessors[current]:
                if pred not in nodes:
                    nodes.add(pred)
                    if pred != header:
                        pending.append(pred)
        loops[header]['latches'].add(latch)
        loops[header]['nodes'].update(nodes)
    memory_accesses = []
    for pc in sorted(reachable):
        op, args = by_pc[pc]
        if op not in ('ldr', 'ldrb', 'ldrh', 'str', 'strb', 'strh'):
            continue
        match = MEMORY.match(args)
        if not match:
            continue
        dst, base, offset, wb, post_index = match.groups()
        shift = re.search(r'lsl\s+#(\d+)', offset or '')
        memory_accesses.append({'pc': hex(pc), 'operation': op,
            'width_bytes': 1 if op.endswith('b') else 2 if op.endswith('h') else 4,
            'base_register': base.strip(), 'index_expression': (offset or '').strip(),
            'scale': 1 << int(shift[1]) if shift else 1,
            'writeback': bool(wb or post_index),
            'address_mode': 'post_index' if post_index else 'pre_index' if wb else 'offset',
            'post_index_increment': int(post_index[1:], 0) if post_index else None,
            'inside_loop_headers': [hex(h) for h, v in sorted(loops.items()) if pc in v['nodes']]})
    results = []
    for header, info in sorted(loops.items()):
        members = info['nodes']
        exits = [{'from': hex(src), 'to': hex(dst)} for src in sorted(members)
                 for dst in sorted(successors[src]) if dst not in members]
        candidates = []
        for latch in sorted(info['latches']):
            op, _ = by_pc[latch]
            prior = next((p for p in predecessors[latch] if p == latch - 4), None)
            if not (op in BRANCHES and prior is not None):
                continue
            cmpop, args = by_pc[prior]
            cmpmatch = IMM.fullmatch(args) if cmpop == 'cmp' else None
            if cmpmatch:
                reg, bound = cmpmatch.groups()
                increments = [hex(pc) for pc in sorted(members)
                              if by_pc[pc] == ('add', f'{reg}, {reg}, #1')]
                candidates.append({'register': reg, 'compare_immediate': int(bound, 0),
                                   'increment_sites': increments, 'branch_condition': op,
                                   'classification': 'counter_candidate_not_proven_induction'})
        results.append({'header': hex(header), 'back_edge_latches': [hex(x) for x in sorted(info['latches'])],
                        'instruction_addresses': [hex(x) for x in sorted(members)],
                        'exit_edges': exits, 'counter_candidates': candidates})
    return {'function': function, 'entry': hex(entry),
            'reachable_instruction_count': len(reachable), 'loop_count': len(results),
            'loops': results, 'memory_accesses': memory_accesses,
            'external_edges': external_edges, 'conditional_returns': conditional_returns,
            'unknown_control_pcs': unknown_control,
            'limitations': 'Dominance-based natural loops of one bounded disassembled function only; registers, pointer aliases, and source-level loops not proven.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--function', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    dis = subprocess.run(['llvm-objdump', '-d', str(args.elf)], capture_output=True, text=True, check=True).stdout
    result = analyze(disassemble_function(dis, args.function), args.function)
    serialized = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding='utf-8')
    print(serialized, end='')


if __name__ == '__main__':
    main()
