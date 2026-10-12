#!/usr/bin/env python3
"""Pattern-limited ARM32 winner reconstruction without ELF symbol names.

Identifies the winner loop in decoded instructions, follows MOVW/MOVT absolute
pointers, and maps virtual addresses via PT_LOAD program headers. Rejects
ambiguous or unsupported candidates. No hardcoded addresses or table contents.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

from recover_winner import INSTRUCTION, composed_address, emit_cpp


def load_segments(data):
    if len(data) < 52 or data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('requires little-endian ELF32')
    phoff = struct.unpack_from('<I', data, 28)[0]
    phentsize, phnum = struct.unpack_from('<HH', data, 42)
    if phentsize < 32 or not phnum or phnum > 512 or phoff + phnum * phentsize > len(data):
        raise ValueError('invalid ELF program headers')
    segments = []
    for n in range(phnum):
        typ, offset, vaddr, _, filesz, memsz, flags, _ = struct.unpack_from(
            '<8I', data, phoff + n * phentsize)
        if typ != 1:
            continue
        if filesz > memsz or offset + filesz > len(data) or vaddr + memsz > 1 << 32:
            raise ValueError('invalid ELF PT_LOAD segment')
        segments.append((vaddr, memsz, offset, filesz, flags))
    if not segments:
        raise ValueError('no loadable ELF segments')
    return segments


def memory_region(data, segments, vaddr, count, required_flags, file_backed):
    if count <= 0 or vaddr < 0 or vaddr + count > (1 << 32):
        raise ValueError('invalid requested virtual address interval')
    for base, memsz, offset, filesz, flags in segments:
        if (flags & required_flags) != required_flags:
            continue
        if base <= vaddr and vaddr + count <= base + memsz:
            if file_backed:
                if vaddr + count > base + filesz:
                    raise ValueError('recovered table outside file-backed region')
                return data[offset + vaddr - base: offset + vaddr - base + count]
            return None
    raise ValueError('reconstructed pointer outside compatible PT_LOAD memory')


def disassembled_instructions(path):
    dump = subprocess.run(['llvm-objdump', '-d', str(path)],
                          capture_output=True, check=True, text=True).stdout
    rows = []
    for line in dump.splitlines():
        m = INSTRUCTION.match(line)
        if m:
            rows.append({'pc': int(m[1], 16), 'op': m[2].lower(),
                         'args': m[3].split('@')[0].strip()})
    if not rows:
        raise ValueError('no ARM instructions in executable sections')
    return rows


def branch_target(ins):
    match = re.match(r'^0x([0-9a-fA-F]+)', ins['args'])
    return int(match[1], 16) if match else None


def recognize(data, segments, rows):
    if len(rows) < 25 or rows[0]['op'] != 'push' or rows[0]['args'] != '{r4, r5, r11, lr}':
        raise ValueError('not a supported winner function entry')
    if rows[-1]['op'] != 'pop' or rows[-1]['args'] != '{r4, r5, r11, pc}':
        raise ValueError('unsupported winner exit')
    pcset = {row['pc'] for row in rows}
    if any(b['pc'] != a['pc'] + 4 for a, b in zip(rows, rows[1:])):
        raise ValueError('non-contiguous ARM instruction candidate')
    bypc = {i['pc']:i for i in rows}
    table_addr = composed_address(rows, 'r12')
    board_addr = composed_address(rows, 'lr')
    # Verify key compiler-specific indexed-load structure and loop shape.
    expected = [
        ('add', 'r2, r1, r1, lsl #1'),
        ('mov', 'r3, r12'),
        ('ldrb', 'r2, [r3, r2]!'),
        ('ldrb', 'r4, [r3, #0x1]'),
        ('ldrb', 'r3, [r3, #0x2]'),
        ('ldr', 'r2, [lr, r2, lsl #2]'),
        ('ldr', 'r4, [lr, r4, lsl #2]'),
        ('ldr', 'r3, [lr, r3, lsl #2]'),
        ('eor', 'r5, r2, r4'),
        ('eor', 'r3, r4, r3'),
        ('orrs', 'r3, r5, r3'),
        ('movwne', 'r3, #0x1'),
        ('clz', 'r4, r2'),
        ('lsr', 'r4, r4, #5'),
        ('orrs', 'r3, r3, r4'),
        ('moveq', 'r0, r2'),
    ]
    actual = [(i['op'], i['args']) for i in rows]
    cursor = 0
    matched = []
    for item in expected:
        try:
            cursor = actual.index(item, cursor) + 1
            matched.append(rows[cursor - 1])
        except ValueError as exc:
            raise ValueError('unsupported ARM loop or boolean test pattern: ' + str(item)) from exc
    if any(b['pc'] != a['pc'] + 4 for a, b in zip(matched, matched[1:])):
        raise ValueError('ARM loop instruction sequence is not contiguous')
    loop_pc = matched[0]['pc']
    bounds = [(i['pc'], int(i['args'].split('#', 1)[1], 0)) for i in rows
              if i['op'] == 'cmp' and re.fullmatch(r'r1, #(0x[0-9a-fA-F]+|\d+)', i['args'])]
    if len(bounds) != 1:
        raise ValueError('loop termination bound missing or ambiguous')
    limit_pc, rows_count = bounds[0]
    if not 1 <= rows_count <= 256:
        raise ValueError('unsupported triplet count')
    bnes = [i for i in rows if i['op'] == 'bne' and branch_target(i) == loop_pc]
    if len(bnes) != 1 or bnes[0]['pc'] != limit_pc + 4:
        raise ValueError('loop back edge does not agree with bound')
    if not any(i['op'] == 'beq' and branch_target(i) == rows[-1]['pc']
               and i['pc'] > matched[-1]['pc'] and i['pc'] < limit_pc
               for i in rows):
        raise ValueError('early winner exit is not evidenced')
    if bypc.get(limit_pc + 8, {}).get('op') != 'mov' or bypc[limit_pc + 8]['args'] != 'r0, #0':
        raise ValueError('missing no-winner return value')
    table_bytes = memory_region(data, segments, table_addr, rows_count * 3, 4, True)
    triplets = [list(table_bytes[i:i+3]) for i in range(0, len(table_bytes), 3)]
    if not triplets or len(triplets) != rows_count:
        raise ValueError('invalid triplet table')
    board_cells = max(max(t) for t in triplets) + 1
    if board_cells > 4096:
        raise ValueError('inferred board too large')
    memory_region(data, segments, board_addr, board_cells * 4, 2, False)
    # All references come from immediate reconstruction and ELF ranges, not symbols.
    return {
        'function': 'winner', 'source': 'ARM32 stripped ELF PT_LOAD + instruction fingerprint',
        'function_address': hex(rows[0]['pc']),
        'board_address': hex(board_addr), 'board_cells': board_cells,
        'table_address': hex(table_addr), 'table_symbol': None,
        'triplets': triplets, 'loop_iterations': rows_count,
        'board_load_pcs': [hex(i['pc']) for i in matched if i['op'] == 'ldr'],
        'table_load_pcs': [hex(i['pc']) for i in matched if i['op'] == 'ldrb'],
        'boolean_test': 'strict_clang_arm_o1_xor_clz_fingerprint',
        'constraints': [
            'Works without ELF symbol names but requires ELF program headers and ARM disassembly',
            'Only matches this clang -O1 winner loop pattern; no generic loop inference',
            'Board length inferred from maximum observed index; excess capacity is unknown',
            'Function signature and semantic C++ skeleton are provided by a template'
        ]
    }


def recover_stripped(path):
    path = Path(path)
    data = path.read_bytes()
    segments = load_segments(data)
    instructions = disassembled_instructions(path)
    results = []
    # Avoid supplied function offsets or symbol names: locate the exact stack
    # prologue/epilogue and validate the complete internal loop fingerprint.
    for i, ins in enumerate(instructions):
        if (ins['op'], ins['args']) != ('push', '{r4, r5, r11, lr}'):
            continue
        for j in range(i+1, min(i+130, len(instructions))):
            if (instructions[j]['op'], instructions[j]['args']) != ('pop', '{r4, r5, r11, pc}'):
                continue
            try:
                found = recognize(data, segments, instructions[i:j+1])
            except ValueError:
                continue
            results.append(found)
            break
    if not results:
        raise ValueError('no supported winner fingerprint in ARM32 ELF')
    if len(results) != 1:
        raise ValueError('ambiguous winner signatures in ARM32 ELF')
    return results[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--cpp', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    result = recover_stripped(args.elf)
    args.cpp.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.cpp.write_text(emit_cpp(result), encoding='utf-8')
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'cpp': str(args.cpp), 'report': str(args.report),
                      'recovered_triplets': result['loop_iterations']}))


if __name__ == '__main__':
    main()
