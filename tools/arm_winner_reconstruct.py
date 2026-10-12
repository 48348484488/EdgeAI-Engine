#!/usr/bin/env python3
"""Conservative, pattern-verified reconstruction of winner() from an ARM32 ELF.

The 8x3 lines table comes from ELF .rodata, not from C source.
Only a specific optimized ARM implementation is recognized. Fail closed otherwise.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess


def _c_string(blob, off):
    end = blob.find(b'\0', off)
    if end < 0:
        raise ValueError('bad ELF string table')
    return blob[off:end].decode('ascii')


def _symbols_and_sections(data):
    if len(data) < 52 or data[:5] != b'\x7fELF\x01' or data[5] != 1:
        raise ValueError('requires ELF32 little-endian')
    if struct.unpack_from('<H', data, 18)[0] != 40:
        raise ValueError('requires ARM ELF')
    shoff, = struct.unpack_from('<I', data, 32)
    shentsize, shnum = struct.unpack_from('<HH', data, 46)
    if shentsize < 40 or not shnum or shoff + shnum * shentsize > len(data):
        raise ValueError('invalid ELF section table')
    hdrs = [struct.unpack_from('<IIIIIIIIII', data, shoff + i * shentsize)
            for i in range(shnum)]
    symbols = {}
    for sh in hdrs:
        _, typ, _, _, off, size, link, _, _, entsize = sh
        if typ != 2:
            continue
        if link >= shnum or entsize < 16 or off + size > len(data):
            raise ValueError('invalid ELF symbol table')
        strings = hdrs[link]
        string_off, string_size = strings[4:6]
        if string_off + string_size > len(data):
            raise ValueError('invalid ELF symbol strings')
        names = data[string_off:string_off + string_size]
        for pos in range(off, off + size, entsize):
            name_off, va, symbol_size, info, other, sec = struct.unpack_from('<IIIBBH', data, pos)
            if name_off < len(names) and sec < shnum:
                name = _c_string(names, name_off)
                if name:
                    symbols[name] = {'address': va, 'size': symbol_size, 'section': sec}
    return symbols, hdrs


def _symbol_bytes(data, symbols, sections, name):
    if name not in symbols:
        raise ValueError('required ARM symbol absent: ' + name)
    s = symbols[name]
    sh = sections[s['section']]
    offset = sh[4] + s['address'] - sh[3]
    if sh[1] == 8 or not sh[3] <= s['address'] <= sh[3] + sh[5]:
        raise ValueError('symbol is not backed by initialized section bytes')
    if offset < sh[4] or offset + s['size'] > sh[4] + sh[5] or offset + s['size'] > len(data):
        raise ValueError('symbol outside ELF section')
    return data[offset:offset + s['size']]


def _disassembly(elf_path):
    out = subprocess.run(['llvm-objdump', '-d', str(elf_path)], check=True,
                         capture_output=True, text=True).stdout
    match = re.search(r'(?ms)^([0-9a-fA-F]+) <winner>:\s*\n(.*?)(?=^[0-9a-fA-F]+ <|\Z)', out)
    if not match:
        raise ValueError('winner() not found in ARM disassembly')
    instructions = []
    for line in match[2].splitlines():
        parsed = re.match(r'^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F]+\s+([a-zA-Z][\w.]*)\s*(.*)$', line)
        if parsed:
            addr, op, operands = parsed.groups()
            instructions.append((int(addr, 16), op.lower(), operands.split('@')[0].strip()))
    return int(match[1], 16), instructions


def _verify_instructions(instructions, table_address, board_address):
    expected = [
        ('mov', 'r1, #0'),
        ('add', 'r2, r1, r1, lsl #1'),
        ('ldrb', 'r2, [r3, r2]!'),
        ('ldrb', 'r4, [r3, #0x1]'),
        ('ldrb', 'r3, [r3, #0x2]'),
        ('ldr', 'r2, [lr, r2, lsl #2]'),
        ('ldr', 'r4, [lr, r4, lsl #2]'),
        ('ldr', 'r3, [lr, r3, lsl #2]'),
        ('eor', 'r5, r2, r4'),
        ('eor', 'r3, r4, r3'),
        ('orrs', 'r3, r5, r3'),
        ('clz', 'r4, r2'),
        ('lsr', 'r4, r4, #5'),
        ('orrs', 'r3, r3, r4'),
        ('moveq', 'r0, r2'),
        ('add', 'r1, r1, #1'),
        ('cmp', 'r1, #8'),
        ('mov', 'r0, #0'),
        ('pop', '{r4, r5, r11, pc}'),
    ]
    pairs = [(op, operands) for _, op, operands in instructions]
    position = 0
    for item in expected:
        try:
            position = pairs.index(item, position) + 1
        except ValueError:
            raise ValueError('unverified winner ARM opcode/ordering: ' + repr(item)) from None
    def pointer(reg):
        vals = []
        for _, op, operands in instructions:
            m = re.fullmatch(rf'{reg}, #(0x[0-9a-fA-F]+|\d+)', operands)
            if m and op in ('movw', 'movt'):
                vals.append((op, int(m[1], 0)))
        if len(vals) != 2 or {op for op, _ in vals} != {'movw', 'movt'}:
            raise ValueError('cannot prove symbol pointer in ' + reg)
        return next(v for op, v in vals if op == 'movw') | (next(v for op, v in vals if op == 'movt') << 16)
    if pointer('r12') != table_address or pointer('lr') != board_address:
        raise ValueError('rodata or board pointer does not match ELF symbols')
    branches = [(pc, operands) for pc, op, operands in instructions if op == 'bne']
    back_edge_pc = next((pc for pc, op, args in instructions if op == 'add' and args == 'r2, r1, r1, lsl #1'), None)
    if len(branches) != 1 or not branches[0][1].startswith(hex(back_edge_pc)):
        raise ValueError('winner loop back-edge was not verified')
    if sum(op == 'beq' for _, op, _ in instructions) != 1:
        raise ValueError('winner early-exit branch was not verified')
    permitted = {'push', 'add', 'mov', 'movw', 'movt', 'ldrb', 'ldr', 'eor',
                 'orrs', 'movwne', 'clz', 'lsr', 'moveq', 'beq', 'cmp', 'bne', 'pop'}
    unexpected = [(hex(pc), op) for pc, op, _ in instructions if op not in permitted]
    if unexpected:
        raise ValueError('unexpected winner opcodes: ' + repr(unexpected))
    return {'instruction_count': len(instructions), 'loop_back_edge': hex(back_edge_pc),
            'table_symbol_address': hex(table_address), 'board_symbol_address': hex(board_address),
            'compiler_pattern': 'LLVM ARM32 -O1 table lookup / XOR equality / CLZ nonzero guard'}


def reconstruct(elf_path):
    elf_path = Path(elf_path)
    data = elf_path.read_bytes()
    syms, sections = _symbols_and_sections(data)
    for name in ('winner', 'board', 'winner.lines'):
        if name not in syms:
            raise ValueError('missing required ELF symbol: ' + name)
    raw = _symbol_bytes(data, syms, sections, 'winner.lines')
    if len(raw) != 24 or any(v > 8 for v in raw):
        raise ValueError('invalid winner lookup table; expected 8x3 positions from 0..8')
    table = [list(raw[i:i + 3]) for i in range(0, 24, 3)]
    entry, instructions = _disassembly(elf_path)
    if entry != syms['winner']['address']:
        raise ValueError('disassembly and ELF symbol disagree on winner entry')
    evidence = _verify_instructions(instructions, syms['winner.lines']['address'], syms['board']['address'])
    lines = ',\n'.join('        {' + ', '.join(map(str, triplet)) + '}' for triplet in table)
    cpp = ("// Constrained reconstruction: table bytes and control flow verified from ARM32 ELF.\n"
           "extern \"C\" volatile int board[9];\n"
           "extern \"C\" int winner(void) {\n"
           "    static const unsigned char lines[8][3] = {\n" + lines + "\n    };\n"
           "    for (int i = 0; i < 8; ++i) {\n"
           "        int a = board[lines[i][0]];\n"
           "        int b = board[lines[i][1]];\n"
           "        int c = board[lines[i][2]];\n"
           "        if (a != 0 && a == b && b == c) return a;\n"
           "    }\n    return 0;\n}\n")
    return {'cpp': cpp, 'evidence': {**evidence, 'winner_address': hex(entry),
            'table_source': 'symbol winner.lines in compiled ELF .rodata',
            'winning_triplets': table, 'byte_count': len(raw),
            'not_inferred': ['C++ signature, type of board and high-level for/if skeleton',
                             'general validity for binaries with other loop implementations']}}


def main():
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument('elf', type=Path)
    arg.add_argument('--output', type=Path, default=Path('results/winner_candidate.cpp'))
    arg.add_argument('--report', type=Path, default=Path('results/winner_arm_evidence.json'))
    args = arg.parse_args()
    result = reconstruct(args.elf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result['cpp'], encoding='utf-8')
    args.report.write_text(json.dumps(result['evidence'], indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'report': str(args.report), 'evidence': result['evidence']}))


if __name__ == '__main__':
    main()
