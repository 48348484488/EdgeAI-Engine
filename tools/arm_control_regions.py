#!/usr/bin/env python3
"""Infer structural branch reconvergence using postdominators of a bounded ARM CFG.

Works on function-independent CFG evidence from arm_loop_analysis.analyze.
This is structural evidence only: it neither proves predicates nor emits C++.
"""
import argparse
from collections import deque
import importlib.util
import json
from pathlib import Path
import subprocess

EXIT = '__function_exit__'


def analyze(report, max_nodes=20000):
    nodes = {int(a, 16) for a in report['reachable_pcs']}
    entry = int(report['entry'], 16)
    if not nodes or entry not in nodes or len(nodes) > max_nodes:
        raise ValueError('invalid or oversized CFG')
    edges = {pc: set() for pc in nodes}
    labels = {}
    for e in report['cfg_edges']:
        src, dst = int(e['from'], 16), int(e['to'], 16)
        if src not in nodes or dst not in nodes:
            raise ValueError('CFG edge outside reachable graph')
        edges[src].add(dst)
        labels[(src, dst)] = e.get('type', 'flow')
    exit_sites = {int(p, 16) for p in report['exit_pcs']}
    if not exit_sites <= nodes:
        raise ValueError('CFG exit not reachable')
    for ret in report.get('conditional_returns', []):
        src = int(ret['pc'], 16)
        if src not in nodes:
            raise ValueError('conditional return outside graph')
        edges[src].add(EXIT)
    for other in report.get('external_edges', []):
        src = int(other['from'], 16)
        if src not in nodes:
            raise ValueError('external exit outside graph')
        edges[src].add(EXIT)
    for src in exit_sites:
        edges[src].add(EXIT)
    for pc in nodes:
        if not edges[pc]:
            edges[pc].add(EXIT)
    edges[EXIT] = set()
    backwards = {pc: set() for pc in (*nodes, EXIT)}
    for src, dests in edges.items():
        for dst in dests:
            backwards[dst].add(src)
    can_exit = {EXIT}
    pending = deque([EXIT])
    while pending:
        curr = pending.popleft()
        for pred in backwards[curr] - can_exit:
            can_exit.add(pred)
            pending.append(pred)
    # Bitsets keep memory linear in the number of CFG nodes, unlike a Python
    # set of all postdominators at every node.
    ordered = [EXIT] + sorted(nodes)
    bit = {pc: 1 << i for i, pc in enumerate(ordered)}
    all_bits = (1 << len(ordered)) - 1
    postdom = {EXIT: bit[EXIT]}
    for pc in nodes:
        postdom[pc] = all_bits if pc in can_exit else bit[pc]
    changed = True
    while changed:
        changed = False
        for pc in sorted(nodes, reverse=True):
            if pc not in can_exit:
                continue
            if any(s not in can_exit for s in edges[pc]):
                updated = bit[pc]
            else:
                intersect = all_bits
                for successor in edges[pc]:
                    intersect &= postdom[successor]
                updated = bit[pc] | intersect
            if updated != postdom[pc]:
                postdom[pc] = updated
                changed = True
    branches = []
    for src in sorted(nodes):
        destinations = edges[src]
        if len(destinations) != 2:
            continue
        # Branches must come from decoded ARM branch labels, not accidental
        # convergence of two arbitrary successor edges.
        taken = next((dst for dst in destinations if labels.get((src, dst)) == 'taken'), None)
        fallthrough = next((dst for dst in destinations if labels.get((src, dst)) == 'fallthrough'), None)
        conditional_return = any(int(x['pc'], 16) == src for x in report.get('conditional_returns', []))
        if conditional_return and EXIT in destinations:
            fallthrough = next(x for x in destinations if x != EXIT)
            taken = EXIT
        if taken is None or fallthrough is None:
            continue
        classification = 'unresolved'
        merge = None
        if taken in can_exit and fallthrough in can_exit:
            common_bits = postdom[taken] & postdom[fallthrough] & ~bit[EXIT]
            common = [v for v in sorted(nodes) if common_bits & bit[v]]
            immediate = [v for v in common if postdom[v] & common_bits == common_bits]
            if len(immediate) == 1:
                merge = hex(immediate[0]); classification = 'reconverging'
            elif not common:
                classification = 'exit_only'
        if report.get('unknown_control_pcs'):
            classification = 'unresolved'
            merge = None
        branches.append({'branch_pc': hex(src), 'taken': EXIT if taken == EXIT else hex(taken),
                         'fallthrough': hex(fallthrough), 'merge': merge, 'classification': classification,
                         'conditional_return': conditional_return})
    return {'entry': report['entry'], 'decision_count': len(branches),
            'decisions': branches, 'nonterminating_nodes': [hex(x) for x in sorted(nodes - can_exit)],
            'unknown_control_pcs': list(report.get('unknown_control_pcs', [])),
            'limitations': 'Postdomination over known static CFG; branches, flags, memory values and termination are not proven.'}


def from_instructions(instructions, function=None):
    path = Path(__file__).with_name('arm_loop_analysis.py')
    spec = importlib.util.spec_from_file_location('edgeai_arm_loops', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return analyze(module.analyze(instructions, function))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--function', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    path = Path(__file__).with_name('arm_loop_analysis.py')
    spec = importlib.util.spec_from_file_location('edgeai_arm_loops', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    disassembly = subprocess.run(['llvm-objdump', '-d', str(args.elf)],
                                 check=True, capture_output=True, text=True).stdout
    report = from_instructions(module.disassemble_function(disassembly, args.function), args.function)
    result = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding='utf-8')
    print(result, end='')


if __name__ == '__main__':
    main()
