#!/usr/bin/env python3
"""Fail-closed source-blind lifter for a bounded AArch64 startup call chain.

Supports only literal no-argument __printf_chk, time(NULL)->srand,
internal terminal(0), and signal(2, internal handler), with a balanced
16-byte frame. The emitted C++ is a *candidate*, not verified equivalence.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from aarch64_printf_lifter import get_cstring, load_rodata, plt_symbols

ROW = re.compile(r'^\s*([0-9a-fA-F]+):\s+([\w.]+)(?:\s+(.*))?$')
ADRP = re.compile(r'^x1, (0x[0-9a-fA-F]+)(?:\s+<[^>]*>)?$')
ADD = re.compile(r'^x1, x1, #(0x[0-9a-fA-F]+|\d+)$')
CALL = re.compile(r'^0x([0-9a-fA-F]+)(?:\s+<[^>]*>)?$')


def disassemble(elf, start, end):
    if start >= end or start % 4 or end % 4 or end - start > 1024:
        raise ValueError('invalid bounded aligned function range')
    cmd = ['llvm-objdump', '-d', '--no-show-raw-insn',
           f'--start-address={start:#x}', f'--stop-address={end:#x}', str(elf)]
    output = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=20).stdout
    rows = []
    for line in output.splitlines():
        m = ROW.match(line)
        if m:
            pc = int(m[1], 16)
            if start <= pc < end:
                rows.append((pc, m[2].lower(), (m[3] or '').split(' //')[0].strip()))
    if [pc for pc, _, _ in rows] != list(range(start, end, 4)):
        raise ValueError('incomplete or noncontiguous disassembly')
    return rows


def lift(rows, rodata, plt, text_addresses):
    if not rows or any(rows[i][0] + 4 != rows[i+1][0] for i in range(len(rows)-1)):
        raise ValueError('noncontiguous function instructions')
    start = rows[0][0]
    i = 0

    def consume(op, args=None):
        nonlocal i
        if i >= len(rows):
            raise ValueError('truncated instruction sequence')
        pc, actual_op, actual_args = rows[i]
        if actual_op != op or (args is not None and actual_args != args):
            raise ValueError(f'unsupported instruction at {pc:#x}: {actual_op} {actual_args}')
        i += 1
        return actual_args

    def literal_pointer():
        base = consume('adrp')
        m = ADRP.fullmatch(base)
        if not m:
            raise ValueError('expected ADRP x1, page')
        delta = consume('add')
        n = ADD.fullmatch(delta)
        if not n:
            raise ValueError('expected ADD x1, x1, immediate')
        return int(m[1], 16) + int(n[1], 0)

    def call():
        arg = consume('bl')
        m = CALL.fullmatch(arg)
        if not m:
            raise ValueError('unresolved direct call target')
        return int(m[1], 16)

    def imported(name):
        addr = call()
        if plt.get(addr) != name:
            raise ValueError(f'expected verified {name}@plt, got {addr:#x}')

    consume('stp', 'x29, x30, [sp, #-0x10]!')
    consume('mov', 'x29, sp')
    literals = []
    while i < len(rows) and rows[i][1] == 'adrp':
        address = literal_pointer()
        consume('mov', 'w0, #0x2')
        imported('__printf_chk')
        literal = get_cstring(address, rodata)
        if b'%' in literal:
            raise ValueError('format arguments unsupported in startup printf')
        literals.append((address, literal))
        if len(literals) > 8:
            raise ValueError('too many startup strings')
    if not literals:
        raise ValueError('no startup literals')
    consume('mov', 'x0, #0x0')
    imported('time')
    imported('srand')
    consume('mov', 'w0, #0x0')
    terminal = call()
    if terminal not in text_addresses or terminal in plt:
        raise ValueError('terminal callback is not a known internal text entry')
    handler = literal_pointer()
    if handler not in text_addresses or handler in plt:
        raise ValueError('signal handler is not a known internal text entry')
    consume('mov', 'w0, #0x2')
    imported('signal')
    consume('ldp', 'x29, x30, [sp], #0x10')
    consume('ret', '')
    if i != len(rows):
        raise ValueError('trailing instructions after return')

    lines = ['// EdgeAI: unvalidated source-blind C++ candidate; bounded AArch64 startup chain.',
             '#include <cstdint>', '#include <ctime>', '#include <cstdlib>', '#include <csignal>',
             'extern "C" int __printf_chk(int, const char*, ...);',
             f'extern "C" void recovered_{terminal:x}(unsigned);',
             f'extern "C" void recovered_{handler:x}(int);',
             f'extern "C" void recovered_{start:x}() {{']
    for index, (_, literal) in enumerate(literals):
        data = ', '.join(f'0x{v:02x}' for v in literal + b'\0')
        lines.append(f'  static const unsigned char literal_{index}[] = {{{data}}};')
        lines.append(f'  __printf_chk(2, reinterpret_cast<const char*>(literal_{index}));')
    lines += ['  const std::time_t seed = std::time(nullptr);',
              '  std::srand(static_cast<unsigned>(seed));',
              f'  recovered_{terminal:x}(0u);',
              f'  std::signal(2, recovered_{handler:x});', '}']
    return '\n'.join(lines) + '\n', {
        'start': hex(start), 'instruction_count': len(rows),
        'literal_addresses': [hex(a) for a, _ in literals],
        'internal_terminal': hex(terminal), 'internal_signal_handler': hex(handler),
        'imported_functions': ['__printf_chk', 'time', 'srand', 'signal'],
        'behaviorally_validated': False, 'executable_game_complete': False,
        'limitations': 'Assumed C++ signatures for internal callbacks; no ARM64 runtime parity or full game linkage.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf', required=True, type=Path)
    p.add_argument('--start', required=True, type=lambda v: int(v, 0))
    p.add_argument('--end', required=True, type=lambda v: int(v, 0))
    p.add_argument('--expected-sha256', required=True)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    a = p.parse_args()
    digest = hashlib.sha256(a.elf.read_bytes()).hexdigest()
    if digest != a.expected_sha256.lower():
        raise ValueError('ELF SHA-256 mismatch')
    rows = disassemble(a.elf, a.start, a.end)
    whole = subprocess.run(['llvm-objdump', '-d', '--no-show-raw-insn', '--section=.text', str(a.elf)],
                           capture_output=True, text=True, check=True, timeout=20).stdout
    addresses = {int(m[1], 16) for line in whole.splitlines() if (m := ROW.match(line))}
    source, report = lift(rows, load_rodata(a.elf), plt_symbols(a.elf), addresses)
    report['binary_sha256'] = digest
    report['generated_cpp_sha256'] = hashlib.sha256(source.encode()).hexdigest()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(source)
    a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(f"candidate {report['start']}: {report['instruction_count']} instructions; "
          f"{len(report['literal_addresses'])} literal prints; 2 internal dependencies; NOT validated")


if __name__ == '__main__':
    main()
