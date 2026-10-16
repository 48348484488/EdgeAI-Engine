#!/usr/bin/env python3
"""Conservative inter-block AArch64 ADRP/ADD table-base reaching definitions.

Performs an all-predecessor constant meet along *explicit* intraprocedural CFG
edges. An unknown path, instruction, register clobber, or differing origin
invalidates the candidate. This is not proof of runtime reachability: the
candidate CFG cannot model outside entry points or unresolved indirect edges.
No binary code is run and no jump-table data is read.
"""
import argparse
from collections import deque
import json
from pathlib import Path
import re

from aarch64_table_provenance import (ADRP, IMM_ADD, NONWRITING,
                                     may_write_register, parse_llvm, reg_id)

MAX_BLOCKS = 10000
MAX_SITES = 128
MAX_INSTRUCTIONS = 250000
MAX_STEPS = 1000000
KNOWN_CONTROL = frozenset(('B', 'B.cond', 'BL', 'BLR', 'BR', 'RET', 'CBZ', 'CBNZ', 'TBZ', 'TBNZ'))
# Operations for which an explicit, conventional destination is understood.
# Unknown mnemonics invalidate the tracked register, even if that is cautious.
DEST_FIRST = frozenset('''adc adcs add adds adr adrp and ands asr asrv bfi bfxil bic
    bics clz cls csel csinc csinv csneg cset csetm eor eon extr ldr ldrb
    ldrh ldrsb ldrsh ldrsw ldur ldurb ldurh ldursb ldursh ldursw lsl lslv
    lsr lsrv madd mov movk movn movz msub mul mvn neg negs orn orr rbit rev
    rev16 rev32 sbfiz sbfm sdiv smaddl smulh sub subs ubfiz ubfm udiv umaddl
    umulh'''.split())


def _parse_hex(value):
    if not isinstance(value, str) or not re.fullmatch(r'0x[0-9a-fA-F]+', value):
        raise ValueError('expected hexadecimal address')
    return int(value, 16)


def _blocks_and_edges(graph):
    if (graph.get('architecture') != 'AArch64' or
        graph.get('code_executed') is not False):
        raise ValueError('requires read-only AArch64 CFG')
    entry = _parse_hex(graph['entry'])
    size = graph['symbol_size_bytes']
    if not isinstance(size, int) or not 4 <= size <= 4 * 1024 * 1024 or size % 4 or entry % 4:
        raise ValueError('invalid function bounds')
    blocks = graph['blocks']
    if not isinstance(blocks, list) or not 1 <= len(blocks) <= MAX_BLOCKS or len(blocks) != graph['block_count']:
        raise ValueError('invalid block count')
    out = {}
    previous = entry
    for block in sorted(blocks, key=lambda b: _parse_hex(b['start'])):
        start = _parse_hex(block['start'])
        end = _parse_hex(block['end_exclusive'])
        if (start != previous or start % 4 or end % 4 or end <= start or
            _parse_hex(block['last_instruction']) != end - 4 or
            block['size_bytes'] != end - start):
            raise ValueError('CFG blocks do not exactly partition function')
        out[start] = (end, block['last_control_transfer'])
        previous = end
    if previous != entry + size:
        raise ValueError('CFG does not cover function')
    edges = graph['edges']
    if not isinstance(edges, list) or len(edges) != graph['edge_count']:
        raise ValueError('invalid edge count')
    successors = {start: set() for start in out}
    unknown_tail = set()
    outgoing = {start: {} for start in out}
    for start, (end, kind) in out.items():
        if kind not in KNOWN_CONTROL and kind is not None:
            raise ValueError('unsupported CFG terminator')
        if kind == 'BR':
            unknown_tail.add(start)
    for e in edges:
        src = _parse_hex(e['from'])
        if src not in out:
            raise ValueError('edge source is not a block')
        dest = _parse_hex(e['to']) if e['to'] is not None else None
        inside = dest is not None and dest in out
        if e['target_in_symbol'] != inside:
            if dest is not None and entry <= dest < entry + size:
                raise ValueError('internal edge is not a block leader')
            if e['target_in_symbol'] is not False:
                raise ValueError('invalid edge locality')
        if e['kind'] in outgoing[src]:
            raise ValueError('duplicate CFG edge kind')
        outgoing[src][e['kind']] = dest
        if inside and e['kind'] not in ('direct_call_site', 'indirect_call_unresolved'):
            successors[src].add(dest)
    # Reject missing fallthrough/taken edges instead of incorrectly proving
    # a base value along only a subset of the branches.
    for start, (end, kind) in out.items():
        has_next = end < entry + size
        expected = {
            None: {'linear_candidate'} if has_next else set(),
            'B': {'unconditional'},
            'B.cond': {'taken_candidate', *(['not_taken_candidate'] if has_next else [])},
            'CBZ': {'taken_candidate', *(['not_taken_candidate'] if has_next else [])},
            'CBNZ': {'taken_candidate', *(['not_taken_candidate'] if has_next else [])},
            'TBZ': {'taken_candidate', *(['not_taken_candidate'] if has_next else [])},
            'TBNZ': {'taken_candidate', *(['not_taken_candidate'] if has_next else [])},
            'BL': {'direct_call_site', *(['call_return_candidate'] if has_next else [])},
            'BLR': {'indirect_call_unresolved', *(['call_return_candidate'] if has_next else [])},
            'BR': {'indirect_jump_unresolved'},
            'RET': {'return_candidate'},
        }[kind]
        if set(outgoing[start]) != expected:
            raise ValueError('incomplete or inconsistent CFG edge kinds')
        if has_next:
            for name in ('not_taken_candidate', 'call_return_candidate', 'linear_candidate'):
                if name in outgoing[start] and outgoing[start][name] != end:
                    raise ValueError('CFG fallthrough edge mismatch')
        for name in ('indirect_jump_unresolved', 'indirect_call_unresolved', 'return_candidate'):
            if name in outgoing[start] and outgoing[start][name] is not None:
                raise ValueError('CFG claims resolved indirect/return edge')
    return entry, out, successors, unknown_tail, outgoing


def _step(state, op, args, tracked_reg, pc):
    if not op:
        return None  # Incomplete disassembly: cannot prove no clobber.
    # AArch64 pre/post-index memory addressing can modify the base register.
    # This is an implicit destination, not the instruction's first operand.
    if re.search(r'\[\s*x' + str(tracked_reg) + r'\b[^]]*\]\s*(?:!|,)', args):
        return None
    if op in ('bl', 'blr'):
        return None if tracked_reg <= 18 or tracked_reg == 30 else state
    if op == 'adrp':
        found = ADRP.fullmatch(args)
        if found and int(found[1]) == tracked_reg:
            page = int(found[2], 16)
            return ('page', page, pc) if page % 4096 == 0 else None
    if op == 'add':
        found = IMM_ADD.fullmatch(args)
        if found and int(found[1]) == tracked_reg:
            if (int(found[2]) == tracked_reg and state is not None and
                    state[0] == 'page'):
                offset = int(found[3], 0)
                if 0 <= offset < 4096:
                    return ('base', state[1] + offset, state[2], pc)
            return None
    if op not in DEST_FIRST and op not in NONWRITING and not op.startswith('b.'):
        return None  # Unknown instruction semantics.
    if may_write_register(op, args, tracked_reg):
        return None
    return state


def _meet(old, new):
    return old if old == new else None


def _track_site(entry, blocks, successors, unknown_tail, code, pc, tracked_reg):
    incoming = {entry: None}
    queue = deque([entry])
    step_count = 0
    before_site = None
    site_seen = False
    reachable_unknown_branches = set()
    while queue:
        start = queue.popleft()
        state = incoming[start]
        end, tail_kind = blocks[start]
        for at in range(start, end, 4):
            step_count += 1
            if step_count > MAX_STEPS:
                raise ValueError('dataflow budget exceeded')
            op, args = code.get(at, ('', ''))
            if at == pc:
                if site_seen:
                    before_site = _meet(before_site, state)
                else:
                    before_site = state
                    site_seen = True
            state = _step(state, op, args, tracked_reg, at)
        if start in unknown_tail and end - 4 != pc:
            reachable_unknown_branches.add(end - 4)
        for dest in successors[start]:
            if dest not in incoming:
                incoming[dest] = state
                queue.append(dest)
            else:
                merged = _meet(incoming[dest], state)
                if merged != incoming[dest]:
                    incoming[dest] = merged
                    queue.append(dest)
    return before_site if site_seen else None, site_seen, reachable_unknown_branches, len(incoming)


def analyze(graph, indirect, llvm_disassembly):
    if (indirect.get('architecture') != 'AArch64' or
        indirect.get('function') != graph.get('function') or
        indirect.get('entry') != graph.get('entry') or
        indirect.get('targets_resolved') is not False):
        raise ValueError('graph and dispatch identity mismatch')
    entry, blocks, successors, unknown_tail, outgoing = _blocks_and_edges(graph)
    code = parse_llvm(llvm_disassembly)
    control_opcodes = {
        'B': ('b',), 'B.cond': None, 'BL': ('bl',), 'BLR': ('blr',),
        'BR': ('br',), 'RET': ('ret',), 'CBZ': ('cbz',), 'CBNZ': ('cbnz',),
        'TBZ': ('tbz',), 'TBNZ': ('tbnz',),
    }
    for start, (end, kind) in blocks.items():
        if kind is None:
            continue
        op, args = code.get(end-4, ('', ''))
        if (op not in control_opcodes[kind] if kind != 'B.cond'
                else not op.startswith('b.')):
            raise ValueError('LLVM and CFG terminator mismatch')
        edge_name = 'unconditional' if kind == 'B' else (
            'direct_call_site' if kind == 'BL' else (
                'taken_candidate' if kind in ('B.cond', 'CBZ', 'CBNZ', 'TBZ', 'TBNZ')
                else None))
        if edge_name is not None:
            match = re.search(r'0x([0-9a-fA-F]+)(?:\s+.*)?$', args)
            if match is None or int(match[1], 16) != outgoing[start][edge_name]:
                raise ValueError('LLVM and CFG direct branch target mismatch')
    count = sum((end - start) // 4 for start, (end, _) in blocks.items())
    if count > MAX_INSTRUCTIONS:
        raise ValueError('instruction budget exceeded')
    sites = indirect['sites']
    if len(sites) > MAX_SITES or len(sites) != indirect['indirect_site_count']:
        raise ValueError('site count invalid')
    rows = []
    for site in sites:
        pc = _parse_hex(site['pc'])
        pattern = site['pattern']
        row = {'pc': hex(pc), 'pattern': pattern,
               'all_runtime_paths_proven': False,
               'indirect_targets_resolved': False}
        if pattern != 'pc_relative_indexed_table_dispatch_candidate':
            row.update({'status': 'NOT_RELATIVE_TABLE', 'reason': 'not_table_dispatch'})
            rows.append(row)
            continue
        reg = reg_id(site['table_base_register'])
        if reg is None:
            raise ValueError('invalid dispatch table register')
        # BR operand is the *destination* register; the table base is
        # independently tracked through the preceding indexed load.
        if pc not in code or code[pc][0] != 'br' or reg_id(code[pc][1]) is None:
            raise ValueError('LLVM indirect branch mismatch')
        if pc not in {end - 4 for end, kind in blocks.values() if kind == 'BR'}:
            raise ValueError('dispatch is not a BR basic-block terminator')
        state, seen, unresolved, reached = _track_site(
            entry, blocks, successors, unknown_tail, code, pc, reg)
        if not seen:
            row.update({'status': 'UNREACHABLE_UNDER_PARTIAL_CFG', 'reason': 'not_reached_from_symbol_entry'})
        elif state is None or state[0] != 'base':
            row.update({'status': 'UNKNOWN_REACHING_BASE',
                        'reason': 'some_modeled_paths_have_no_common_ADRP_ADD_origin'})
        else:
            row.update({'status': 'STATIC_CFG_BASE_CANDIDATE',
                        'table_base_register': 'x' + str(reg),
                        'table_base_candidate': hex(state[1]),
                        'adrp_pc': hex(state[2]), 'add_pc': hex(state[3]),
                        'explicit_cfg_paths_agree': True,
                        'unknown_indirect_predecessor_risk': bool(unresolved),
                        'unresolved_reachable_other_branches': [hex(x) for x in sorted(unresolved)[:12]],
                        'cfg_is_only_partial': True})
        row['reachable_block_count_in_partial_cfg'] = reached
        rows.append(row)
    return {'status': 'EDGEAI_AARCH64_CFG_TABLE_BASE_DATAFLOW',
            'architecture': 'AArch64', 'function': graph['function'],
            'entry': hex(entry), 'site_count': len(rows),
            'static_cfg_base_candidates': sum(x['status'] == 'STATIC_CFG_BASE_CANDIDATE' for x in rows),
            'sites': rows, 'code_executed': False, 'table_bytes_read': False,
            'runtime_control_flow_proven': False, 'indirect_targets_resolved': False,
            'limitations': [
                'Meet across explicitly modeled CFG edges only; paths entering mid-function may exist.',
                'Unresolved indirect jumps are not connected to unknown destinations.',
                'Conservative register clobbers; no dynamic program execution.',
                'Table base is not a validated index bound or jump-table destination.',
            ]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('cfg_json', type=Path)
    p.add_argument('indirect_json', type=Path)
    p.add_argument('llvm_disassembly', type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    report = analyze(json.loads(args.cfg_json.read_text()),
                     json.loads(args.indirect_json.read_text()),
                     args.llvm_disassembly.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'sites'}, indent=2))


if __name__ == '__main__':
    main()
