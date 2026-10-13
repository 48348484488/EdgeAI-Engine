#!/usr/bin/env python3
"""Recover a supported winner() candidate from ARM32 ELF bytes and disassembly.

This is a strict pattern recognizer for this compiler output, NOT a generic
source-code decompiler. It does not read the original C source to generate C++.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

INSTRUCTION = re.compile(r'^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F]{8}\s+([a-z][a-z0-9]*)\s*(.*?)\s*$')
SYMBOL_HEADER = re.compile(r'^([0-9a-fA-F]+) <([^>]+)>:', re.M)


def elf_symbols(data):
    if len(data) < 52 or data[:6] != b'\x7fELF\x01\x01':
        raise ValueError('requires little-endian ELF32')
    shoff = struct.unpack_from('<I', data, 32)[0]
    shentsize, shnum = struct.unpack_from('<HH', data, 46)
    if shentsize < 40 or not shnum or shoff + shnum * shentsize > len(data):
        raise ValueError('malformed section header table')
    sections = [struct.unpack_from('<10I', data, shoff + i * shentsize) for i in range(shnum)]
    result = {}
    for typ, name, offset, size, link, entsize in ((s[1], s[0], s[4], s[5], s[6], s[9]) for s in sections):
        if typ != 2:
            continue
        if link >= len(sections) or entsize < 16 or offset + size > len(data):
            raise ValueError('bad ELF symbol table')
        strings = sections[link]
        st_off, st_size = strings[4], strings[5]
        if st_off + st_size > len(data):
            raise ValueError('bad ELF string table')
        names = data[st_off:st_off + st_size]
        for at in range(offset, offset + size, entsize):
            if at + 16 > len(data):
                raise ValueError('truncated symbol')
            name_off, value, sym_size, info, other, secidx = struct.unpack_from('<IIIBBH', data, at)
            if name_off >= len(names):
                continue
            symbol_name = names[name_off:].split(b'\x00', 1)[0].decode('utf-8', 'replace')
            if not symbol_name or secidx >= len(sections) or secidx == 0:
                continue
            sec = sections[secidx]
            sec_addr, sec_offset, sec_size = sec[3], sec[4], sec[5]
            if value < sec_addr or value + sym_size > sec_addr + sec_size:
                continue
            file_offset = sec_offset + (value - sec_addr)
            if sec[1] == 8:  # SHT_NOBITS (e.g. .bss)
                payload = None
            else:
                if file_offset + sym_size > len(data):
                    raise ValueError('truncated ELF symbol data')
                payload = data[file_offset:file_offset + sym_size]
            result[symbol_name] = {'address': value, 'size': sym_size, 'data': payload}
    return result


def instructions_for(disassembly, function):
    matches = list(SYMBOL_HEADER.finditer(disassembly))
    for i, m in enumerate(matches):
        if m.group(2) != function:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(disassembly)
        rows = []
        for line in disassembly[m.end():end].splitlines():
            item = INSTRUCTION.match(line)
            if item:
                rows.append({'pc': int(item[1], 16), 'op': item[2].lower(),
                             'args': item[3].split('@')[0].strip()})
        if not rows:
            raise ValueError('symbol has no disassembled instructions')
        return rows
    raise ValueError('winner function symbol missing')


def composed_address(rows, register):
    lower = next((x for x in rows if x['op'] == 'movw' and
                  re.fullmatch(re.escape(register) + r', #(?:0x[0-9a-fA-F]+|\d+)', x['args'])), None)
    upper = next((x for x in rows if x['op'] == 'movt' and
                  re.fullmatch(re.escape(register) + r', #(?:0x[0-9a-fA-F]+|\d+)', x['args'])), None)
    if lower is None or upper is None or lower['pc'] >= upper['pc']:
        raise ValueError('base address not reconstructible from MOVW/MOVT')
    return int(lower['args'].split('#')[1], 0) | (int(upper['args'].split('#')[1], 0) << 16)


def recover(elf_path):
    path = Path(elf_path)
    symbols = elf_symbols(path.read_bytes())
    board = symbols.get('board')
    table = symbols.get('winner.lines')
    if not board or not table or not table['data']:
        raise ValueError('requires board and winner.lines ELF symbols (not stripped)')
    if board['size'] % 4 or table['size'] % 3 or table['size'] < 3:
        raise ValueError('symbol sizes do not match int board and byte triplets')
    rows = [list(table['data'][k:k+3]) for k in range(0, table['size'], 3)]
    if any(index >= board['size'] // 4 for row in rows for index in row):
        raise ValueError('table references outside board')
    disassembly = subprocess.run(['llvm-objdump', '-d', str(path)],
                                 check=True, capture_output=True, text=True).stdout
    ins = instructions_for(disassembly, 'winner')
    if composed_address(ins, 'lr') != board['address'] or composed_address(ins, 'r12') != table['address']:
        raise ValueError('ARM references do not match ELF board/table symbols')
    board_reads = [x for x in ins if x['op'] == 'ldr' and
                   re.fullmatch(r'r\d+, \[lr, r\d+, lsl #2\]', x['args'])]
    table_reads = [x for x in ins if x['op'] == 'ldrb']
    if len(board_reads) != 3 or len(table_reads) != 3:
        raise ValueError('expected exactly three table-indexed board loads')
    loop_checks = [x for x in ins if x['op'] == 'cmp' and x['args'] == f'r1, #{len(rows)}']
    back_edges = [x for x in ins if x['op'] == 'bne' and
                  (re.match(r'^0x([0-9a-fA-F]+)', x['args']) and
                   int(re.match(r'^0x([0-9a-fA-F]+)', x['args'])[1], 16) < x['pc'])]
    if not loop_checks or not back_edges:
        raise ValueError('loop bound and backward branch not evidenced')
    # Exact compiler fingerprint for (a != 0 && a == b && b == c):
    # clang -O1 combines XOR differences and a CLZ-based zero test.
    fingerprints = {
        'llvm17_xor_clz': [
            ('eor', 'r5, r2, r4'), ('eor', 'r3, r4, r3'),
            ('orrs', 'r3, r5, r3'), ('movwne', 'r3, #0x1'),
            ('clz', 'r4, r2'), ('lsr', 'r4, r4, #5'),
            ('orrs', 'r3, r3, r4'), ('moveq', 'r0, r2')
        ],
        'llvm18_xor_clz': [
            ('eor', 'r5, r2, r4'), ('eor', 'r3, r4, r3'),
            ('orr', 'r3, r5, r3'), ('clz', 'r3, r3'),
            ('lsr', 'r3, r3, #5'), ('cmp', 'r2, #0'),
            ('mov', 'r4, r2'), ('movwne', 'r4, #0x1'),
            ('ands', 'r3, r3, r4'), ('movne', 'r0, r2'),
            ('cmp', 'r3, #1')
        ]
    }
    actual = [(x['op'], x['args']) for x in ins]
    matched_fingerprint = None
    for fingerprint, pattern in fingerprints.items():
        cursor = 0
        try:
            for expected in pattern:
                cursor = actual.index(expected, cursor) + 1
        except ValueError:
            continue
        matched_fingerprint = fingerprint
        break
    if matched_fingerprint is None:
        raise ValueError('unsupported winner boolean-test pattern (LLVM17/LLVM18)')
    # The exact ARM instruction schedule, flags and branch targets must be
    # independently confirmed by the stricter full-function verifier.
    from arm_winner_reconstruct import _verify_instructions
    _verify_instructions(
        [(x['pc'], x['op'], x['args']) for x in ins],
        table['address'], board['address']
    )
    if not any(x['op'] == 'mov' and x['args'] == 'r0, #0' for x in ins):
        raise ValueError('zero fallback missing')
    return {
        'function': 'winner', 'source': 'ARM32 ELF symbol bytes and LLVM disassembly',
        'board_address': hex(board['address']), 'board_cells': board['size'] // 4,
        'table_address': hex(table['address']), 'table_symbol': 'winner.lines',
        'triplets': rows, 'loop_iterations': len(rows),
        'board_load_pcs': [hex(x['pc']) for x in board_reads],
        'table_load_pcs': [hex(x['pc']) for x in table_reads],
        'boolean_test': matched_fingerprint,
        'constraints': [
            'Relies on unstripped ELF symbol names board and winner.lines',
            'Recognizes a specific clang ARM -O1 instruction pattern',
            'C++ signature and semantic pattern are provided by the decompiler'
        ]
    }


def emit_cpp(result):
    rows = result['triplets']
    if not rows or any(len(row) != 3 for row in rows):
        raise ValueError('invalid recovered table')
    lines = [
        '// Pattern-constrained C++ reconstruction from compiled ARM32 ELF.',
        'extern "C" volatile int board[' + str(result['board_cells']) + '];',
        'extern "C" int winner(void) {',
        '    static const unsigned char recovered_lines[][3] = {'
    ]
    lines += ['        {' + ', '.join(map(str, row)) + '},' for row in rows]
    lines.extend([
        '    };',
        '    for (unsigned i = 0; i < ' + str(len(rows)) + '; ++i) {',
        '        const int a = board[recovered_lines[i][0]];',
        '        const int b = board[recovered_lines[i][1]];',
        '        const int c = board[recovered_lines[i][2]];',
        '        if (a != 0 && a == b && b == c) return a;',
        '    }',
        '    return 0;',
        '}', ''
    ])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--cpp', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = recover(args.elf)
    args.cpp.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.cpp.write_text(emit_cpp(result), encoding='utf-8')
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'cpp': str(args.cpp), 'report': str(args.report),
                      'triplets': len(result['triplets']),
                      'board_loads': len(result['board_load_pcs'])}))


if __name__ == '__main__':
    main()
