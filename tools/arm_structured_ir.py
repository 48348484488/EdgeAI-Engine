"""Conservative control-structure IR from ARM natural-loop and postdominator reports.

Only emits an if/else when both arms are linear, disjoint and join at a
postdominator; loops require a proven natural-loop back edge. Source-level
conditions, types and C++ statements remain unresolved.
"""


def build(cfg, regions, max_nodes=20000):
    if cfg.get('entry') != regions.get('entry'):
        raise ValueError('mismatched CFG and postdominator evidence')
    vertices = {int(pc, 16) for pc in cfg['reachable_pcs']}
    if not vertices or len(vertices) > max_nodes:
        raise ValueError('invalid CFG size')
    successors = {pc: set() for pc in vertices}
    for edge in cfg['cfg_edges']:
        src, dst = int(edge['from'], 16), int(edge['to'], 16)
        if src not in vertices or dst not in vertices:
            raise ValueError('edge outside CFG')
        successors[src].add(dst)
    if cfg.get('unknown_control_pcs') or regions.get('unknown_control_pcs'):
        return {'entry': cfg['entry'], 'loops': [], 'conditionals': [],
                'unstructured': [], 'proof_status': 'unknown_control_flow',
                'note': 'No structuring claims with unresolved indirect control flow'}

    loops = []
    for loop in cfg['loops']:
        header = int(loop['header'], 16)
        members = {int(pc, 16) for pc in loop['instruction_addresses']}
        latches = {int(pc, 16) for pc in loop['back_edge_latches']}
        if not members or header not in members or not latches <= members:
            raise ValueError('invalid natural-loop report')
        if any(header not in successors[latch] for latch in latches):
            raise ValueError('loop back edge not in CFG')
        exits = []
        for src in sorted(members):
            for dst in sorted(successors[src] - members):
                exits.append({'from': hex(src), 'to': hex(dst)})
        loops.append({'kind': 'natural_loop', 'header': hex(header),
                      'latches': [hex(p) for p in sorted(latches)],
                      'body_pcs': [hex(p) for p in sorted(members)],
                      'exit_edges': exits, 'parent_header': None,
                      'semantics': 'counter_condition_and_loop_body_not_proven',
                      '_members': members})
    for loop in loops:
        parents = [other for other in loops if loop['_members'] < other['_members']]
        if parents:
            parent = min(parents, key=lambda x: len(x['_members']))
            loop['parent_header'] = parent['header']

    def trace_arm(start, join):
        """Return exact interior PCs of a simple, non-branching arm, or None."""
        current = start
        seen = set()
        output = []
        while current != join:
            if current not in vertices or current in seen:
                return None
            seen.add(current)
            output.append(current)
            dests = successors[current]
            if len(dests) != 1:
                return None
            current = next(iter(dests))
        return output

    decisions = []
    unstructured = []
    decision_addresses = set()
    for decision in regions['decisions']:
        pc = int(decision['branch_pc'], 16)
        if pc not in vertices:
            raise ValueError('decision outside CFG')
        if pc in decision_addresses:
            raise ValueError('duplicate decision')
        decision_addresses.add(pc)
        taken = decision['taken']
        fallthrough = decision['fallthrough']
        for dest in (taken, fallthrough):
            if dest == '__function_exit__':
                continue
            target = int(dest, 16)
            if target not in vertices or target not in successors[pc]:
                raise ValueError('decision edge is not present in CFG')
        inside = [lp for lp in loops if pc in lp['_members']]
        innermost = min(inside, key=lambda lp: len(lp['_members'])) if inside else None
        classification = decision['classification']
        joined = decision.get('merge')
        # Backedge condition belongs to a loop, not an if/else.
        is_latch = next((lp for lp in inside if pc in
                         {int(x, 16) for x in lp['latches']}), None)
        if is_latch:
            decisions.append({'kind': 'loop_branch', 'branch_pc': hex(pc),
                              'loop_header': is_latch['header'],
                              'taken': taken, 'fallthrough': fallthrough,
                              'semantics': 'branch_predicate_unresolved'})
            continue
        if classification == 'reconverging' and joined and not decision.get('conditional_return'):
            merge = int(joined, 16)
            if merge not in vertices:
                raise ValueError('merge outside CFG')
            left = trace_arm(int(taken, 16), merge)
            right = trace_arm(int(fallthrough, 16), merge)
            # The arms cannot overlap before their merge. Do not invent
            # an if/else by crossing a loop boundary or branch in an arm.
            if left is not None and right is not None and not (set(left) & set(right)) and (left or right):
                if not innermost or all(p in innermost['_members'] for p in left + right + [merge]):
                    decisions.append({'kind': 'if_else', 'branch_pc': hex(pc),
                                      'then_pcs': [hex(p) for p in left],
                                      'else_pcs': [hex(p) for p in right],
                                      'merge': hex(merge),
                                      'inside_loop': innermost['header'] if innermost else None,
                                      'semantics': 'condition_and_instructions_unresolved'})
                    continue
        if classification == 'exit_only':
            decisions.append({'kind': 'exit_dispatch', 'branch_pc': hex(pc),
                              'taken': taken, 'fallthrough': fallthrough,
                              'semantics': 'branch_conditions_and_return_values_unresolved'})
            continue
        unstructured.append({'kind': 'unstructured_branch', 'branch_pc': hex(pc),
                             'taken': taken, 'fallthrough': fallthrough,
                             'why': classification})

    for loop in loops:
        del loop['_members']
    return {'entry': cfg['entry'], 'loops': loops,
            'conditionals': decisions, 'unstructured': unstructured,
            'proof_status': 'structural_only',
            'note': 'Control regions are not equivalent C++ source; unknown conditions are not guessed'}


def analyze_instructions(instructions, function=None):
    """Connect existing generic CFG and postdominator passes to this IR."""
    from pathlib import Path
    import importlib.util

    def load(name):
        path = Path(__file__).with_name(name + '.py')
        spec = importlib.util.spec_from_file_location('edgeai_' + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    loops = load('arm_loop_analysis')
    regions = load('arm_control_regions')
    cfg = loops.analyze(instructions, function)
    # Preserve the previous proven control-flow outline. This next pass only
    # attaches decoded effects; it never promotes opcode shapes to C++ proof.
    semantic = load('arm_semantic_ir')
    return semantic.attach(build(cfg, regions.analyze(cfg)), instructions,
                           reachable_pcs=cfg['reachable_pcs'])


def main():
    """Generate a bounded JSON structural outline from an LLVM ARM ELF."""
    import argparse
    import json
    from pathlib import Path
    import subprocess
    import importlib.util
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--function', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    path = Path(__file__).with_name('arm_loop_analysis.py')
    spec = importlib.util.spec_from_file_location('edgeai_loop', path)
    loops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loops)
    dump = subprocess.run(['llvm-objdump', '-d', str(args.elf)],
                          check=True, capture_output=True, text=True).stdout
    result = analyze_instructions(loops.disassemble_function(dump, args.function), args.function)
    serialized = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding='utf-8')
    print(serialized, end='')


if __name__ == '__main__':
    main()
