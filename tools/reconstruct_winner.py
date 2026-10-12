#!/usr/bin/env python3
"""Recover a *specific verified* ARMv7 tic-tac-toe winner loop from an ELF.

Strictly rejects unrecognized compiler layouts, wrong table addresses or
unexpected instructions. This is pattern-based recovery, not general decompilation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def objdump(elf, *args):
    return subprocess.run(['llvm-objdump', *args, str(elf)], check=True,
                          capture_output=True, text=True).stdout


def sections(elf):
    result = {}
    for match in re.finditer(r'^\s*\d+\s+(\.\w+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+',
                             objdump(elf, '-h'), re.M):
        result[match[1]] = {'size': int(match[2], 16), 'address': int(match[3], 16)}
    return result


def instructions(elf, name):
    dump = objdump(elf, '-d')
    block = re.search(r'(?ms)^[0-9a-fA-F]+ <' + re.escape(name) + r'>:\n(.*?)(?=^[0-9a-fA-F]+ <|\Z)', dump)
    if not block:
        raise ValueError('function ' + name + ' absent from ELF disassembly')
    values = []
    for line in block[1].splitlines():
        match = re.match(r'^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F]+\s+([a-z][a-z0-9]*)\s*(.*)$', line)
        if match:
            values.append({'pc': int(match[1], 16), 'op': match[2],
                           'args': match[3].split('@')[0].strip()})
    return values


def section_bytes(elf, name):
    dump = objdump(elf, '-s', '-j', name)
    values = {}
    for line in dump.splitlines():
        match = re.match(r'^\s*([0-9a-fA-F]+)\s+((?:[0-9a-fA-F]{8}(?:\s+|$)){1,4})', line)
        if match:
            base = int(match[1], 16)
            bs = bytes.fromhex(match[2])
            values.update((base + k, byte) for k, byte in enumerate(bs))
    if not values:
        raise ValueError('section ' + name + ' has no extractable bytes')
    return values


def combined_register_address(code, register):
    parts = {}
    for kind in ('movw', 'movt'):
        pattern = re.compile(r'^' + re.escape(register) + r',\s*#(0x[0-9a-fA-F]+|\d+)$')
        vals = [int(match[1], 0) for ins in code if ins['op'] == kind
                if (match := pattern.fullmatch(ins['args']))]
        if len(vals) != 1 or vals[0] > 0xffff:
            raise ValueError('missing/ambiguous ' + kind + ' base for ' + register)
        parts[kind] = vals[0]
    return (parts['movt'] << 16) | parts['movw']


# Verified clang -O1 ARM sequence: CLZ+LSR implements the zero-cell test;
# EQ flags check three equal values; BNE is the eight-iteration loop edge.
# Unsupported instructions cannot silently pass as proof.
LOOP_PATTERN = [
    ('add', r'r2, r1, r1, lsl #1'),
    ('mov', r'r3, r12'),
    ('ldrb', r'r2, \[r3, r2\]!'),
    ('ldrb', r'r4, \[r3, #0x1\]'),
    ('ldrb', r'r3, \[r3, #0x2\]'),
    ('ldr', r'r2, \[lr, r2, lsl #2\]'),
    ('ldr', r'r4, \[lr, r4, lsl #2\]'),
    ('ldr', r'r3, \[lr, r3, lsl #2\]'),
    ('eor', r'r5, r2, r4'),
    ('eor', r'r3, r4, r3'),
    ('orrs', r'r3, r5, r3'),
    ('movwne', r'r3, #0x1'),
    ('clz', r'r4, r2'),
    ('lsr', r'r4, r4, #5'),
    ('orrs', r'r3, r3, r4'),
    ('moveq', r'r0, r2'),
    ('beq', r'(0x[0-9a-fA-F]+) <winner\+0x[0-9a-fA-F]+>'),
    ('add', r'r1, r1, #1'),
    ('cmp', r'r1, #8'),
    ('bne', r'(0x[0-9a-fA-F]+) <winner\+0x[0-9a-fA-F]+>'),
    ('mov', r'r0, #0'),
    ('pop', r'\{r4, r5, r11, pc\}'),
]


def reconstruct(elf):
    elf = Path(elf)
    code = instructions(elf, 'winner')
    start = next((i for i, ins in enumerate(code) if ins['op'] == 'add' and
                  ins['args'] == 'r2, r1, r1, lsl #1'), -1)
    if start < 0 or len(code) - start != len(LOOP_PATTERN):
        raise ValueError('unrecognized winner loop extent')
    if not any(ins['op'] == 'mov' and ins['args'] == 'r1, #0' for ins in code[:start]):
        raise ValueError('no verified loop initialization')
    for ins, (op, pat) in zip(code[start:], LOOP_PATTERN):
        if ins['op'] != op or not re.fullmatch(pat, ins['args']):
            raise ValueError('unsupported winner instruction at ' + hex(ins['pc']) + ': ' + ins['op'] + ' ' + ins['args'])
    eq_target = int(re.match(LOOP_PATTERN[16][1], code[start + 16]['args'])[1], 16)
    back_target = int(re.match(LOOP_PATTERN[19][1], code[start + 19]['args'])[1], 16)
    if eq_target != code[-1]['pc'] or back_target != code[start]['pc']:
        raise ValueError('unexpected loop or equality branch target')
    sec = sections(elf)
    if '.rodata' not in sec or '.bss' not in sec:
        raise ValueError('missing table or board section')
    table_addr = combined_register_address(code[:start], 'r12')
    board_addr = combined_register_address(code[:start], 'lr')
    ro = sec['.rodata']
    bss = sec['.bss']
    if not (ro['address'] <= table_addr and table_addr + 24 <= ro['address'] + ro['size']):
        raise ValueError('table pointer does not map inside .rodata')
    if not (bss['address'] <= board_addr and board_addr + 36 <= bss['address'] + bss['size']):
        raise ValueError('board pointer does not map inside .bss')
    memory = section_bytes(elf, '.rodata')
    try:
        raw = bytes(memory[table_addr + i] for i in range(24))
    except KeyError as exc:
        raise ValueError('missing table data in .rodata') from exc
    rows = [list(raw[i:i+3]) for i in range(0, len(raw), 3)]
    if any(value > 8 for row in rows for value in row):
        raise ValueError('invalid board index in recovered table')
    cpp = ('// Strict ARM32 loop/table pattern; source code was not used for table data.\n'
           'extern "C" volatile int board[9];\n'
           'extern "C" int winner(void) {\n'
           '    static const unsigned char lines[8][3] = {\n' +
           ''.join('        {' + ', '.join(map(str, row)) + '},\n' for row in rows) +
           '    };\n'
           '    for (int i=0; i<8; ++i) {\n'
           '        const int a = board[lines[i][0]];\n'
           '        const int b = board[lines[i][1]];\n'
           '        const int c = board[lines[i][2]];\n'
           '        if (a != 0 && a == b && b == c) return a;\n'
           '    }\n'
           '    return 0;\n'
           '}\n')
    return cpp, {
        'method': 'strict_arm32_loop_pattern_and_elf_rodata',
        'elf_sha256': hashlib.sha256(elf.read_bytes()).hexdigest(),
        'winner_pc': hex(code[0]['pc']),
        'table_address': hex(table_addr),
        'board_address': hex(board_addr),
        'table_bytes_sha256': hashlib.sha256(raw).hexdigest(),
        'rows': rows,
        'loop_iterations': 8,
        'loop_back_edge': [hex(code[start + 19]['pc']), hex(back_target)],
        'early_return_pc': hex(eq_target),
        'verified_instructions': len(code),
        'limits': 'Only this proven ARM32 clang-O1 code pattern; C++ signature/board declaration provided.'
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--output', type=Path, default=Path('results/winner_candidate.cpp'))
    parser.add_argument('--metadata', type=Path, default=Path('results/winner_candidate.json'))
    args = parser.parse_args()
    cpp, report = reconstruct(args.elf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(cpp, encoding='utf-8')
    args.metadata.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
