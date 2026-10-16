#!/usr/bin/env python3
"""Conservatively recover AArch64 no-argument printf wrappers from stripped ELF.

Reads .text, allocated read-only ELF data, and dynamic PLT name annotations.
No original source or .symtab is consumed. Does not support arbitrary libc
calls, unknown formats, unbalanced frames, or variable-dependent arguments.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
from aarch64_stripped_discovery import analyze
from aarch64_leaf_lifter import parse_instructions

MOV = re.compile(r'^(w|x)([0-7]), #((?:0x)?[0-9a-fA-F]+)$')
ADRP = re.compile(r'^x([0-7]), (0x[0-9a-fA-F]+)$')
ADD = re.compile(r'^x([0-7]), x([0-7]), #((?:0x)?[0-9a-fA-F]+)$')
PRINTF = re.compile(r'^0x[0-9a-fA-F]+$')
OPEN = re.compile(r'^x29, x30, \[sp, #-(0x[0-9a-fA-F]+|\d+)\]!$')
CLOSE = re.compile(r'^x29, x30, \[sp\], #(0x[0-9a-fA-F]+|\d+)$')


def plt_symbols(elf):
    """Recover dynamic-linker stub names from the stripped ELF .plt."""
    result = subprocess.run(['llvm-objdump', '-d', '--no-show-raw-insn',
                             '--section=.plt', str(elf)], capture_output=True,
                            text=True, timeout=20, check=True)
    mapping = {}
    for m in re.finditer(r'^\s*([0-9a-fA-F]{5,}):?\s+<([^>]+)@plt>:',
                         result.stdout, re.M):
        mapping[int(m[1], 16)] = m[2]
    if not mapping:
        raise ValueError('no trusted dynamic PLT symbol annotations')
    return mapping


def load_rodata(elf):
    """Use ELF64 section headers to extract precisely bounded read-only bytes."""
    data = Path(elf).read_bytes()
    if data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('requires AArch64 ELF64 little endian')
    hdr = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    if hdr[1] != 183 or hdr[2] != 1 or not 1 <= hdr[11] <= 4096 or hdr[10] < 64:
        raise ValueError('invalid AArch64 section metadata')
    shoff, entsize, count, nameix = hdr[5], hdr[10], hdr[11], hdr[12]
    if nameix >= count or shoff + entsize * count > len(data):
        raise ValueError('section headers outside file')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff+i*entsize)
                for i in range(count)]
    names = sections[nameix]
    if names[4] + names[5] > len(data):
        raise ValueError('bad section name table')
    table = data[names[4]:names[4]+names[5]]
    accepted = []
    for sec in sections:
        idx, stype, flags, addr, off, size, *_ = sec
        if idx >= len(table):
            raise ValueError('invalid section name')
        name = table[idx:].split(b'\0', 1)[0]
        if name == b'.rodata':
            if stype != 1 or not flags & 2 or flags & 4 or size > 1 << 20 or off+size > len(data):
                raise ValueError('not a bounded allocated non-executable rodata')
            accepted.append((addr, data[off:off+size]))
    if len(accepted) != 1:
        raise ValueError('requires one .rodata')
    return accepted[0]


def get_cstring(addr, rodata, cap=1024):
    start, data = rodata
    offset = addr-start
    if not 0 <= offset < len(data):
        raise ValueError('format pointer outside ELF .rodata')
    end = data.find(b'\x00', offset, min(offset+cap+1, len(data)))
    if end < 0:
        raise ValueError('format string not NUL terminated under budget')
    fmt = data[offset:end]
    if not fmt:
        raise ValueError('empty printf format')
    return fmt


def format_arg_count(data):
    """Allow only literal %, %% and bounded decimal %d with optional digits/flags."""
    text = data.decode('utf-8', errors='strict')
    i = 0
    count = 0
    while i < len(text):
        if text[i] != '%':
            i += 1
            continue
        if i+1 < len(text) and text[i+1] == '%':
            i += 2
            continue
        m = re.match(r'%[-+ 0#]*\d{0,3}(?:\.\d{1,3})?d', text[i:])
        if not m:
            raise ValueError('unsupported printf format specifier')
        count += 1
        i += len(m.group())
    if count > 4:
        raise ValueError('too many format operands')
    return count


def _params_ascii(data):
    return ','.join(f'0x{v:02x}' for v in data+b'\x00')


def lift(elf, entry, stop):
    rodata = load_rodata(elf)
    plt = plt_symbols(elf)
    rows = parse_instructions(elf, entry, stop)
    if len(rows) < 7 or len(rows) > 128 or rows[-1][1:] != ('ret', ''):
        raise ValueError('not a bounded returning terminal wrapper')
    first = OPEN.fullmatch(rows[0][2]) if rows[0][1] == 'stp' else None
    last = CLOSE.fullmatch(rows[-2][2]) if rows[-2][1] == 'ldp' else None
    if not first or not last or int(first[1], 0) != int(last[1], 0) or int(first[1], 0) > 256:
        raise ValueError('not a balanced x29/x30 stack frame')
    if rows[1][1:] != ('mov', 'x29, sp'):
        raise ValueError('requires simple FP setup')
    registers = {}
    calls = []
    for pc, op, args in rows[2:-2]:
        if op == 'mov':
            m = MOV.fullmatch(args)
            if not m:
                raise ValueError('unknown mov at ' + hex(pc) + ': ' + args)
            registers[int(m[2])] = int(m[3], 0)
        elif op == 'adrp':
            m = ADRP.fullmatch(args)
            if not m:
                raise ValueError('unknown adrp at ' + hex(pc))
            n, value = int(m[1]), int(m[2], 0)
            if value % 4096:
                raise ValueError('ADRP destination not page-aligned')
            registers[n] = value
        elif op == 'add':
            m = ADD.fullmatch(args)
            if not m or int(m[2]) not in registers:
                raise ValueError('unknown add register source ' + hex(pc))
            dst, src, value = int(m[1]), int(m[2]), int(m[3], 0)
            if value > 4095:
                raise ValueError('unsupported add offset')
            registers[dst] = registers[src] + value
        elif op == 'bl':
            if not PRINTF.fullmatch(args) or plt.get(int(args, 16)) != '__printf_chk':
                raise ValueError('unsupported BL import ' + args)
            if registers.get(0) != 2 or 1 not in registers:
                raise ValueError('cannot prove __printf_chk flag and format pointer')
            fmt = get_cstring(registers[1], rodata)
            count = format_arg_count(fmt)
            args_num = []
            for n in range(2, 2+count):
                if n not in registers:
                    raise ValueError('unknown printf variadic argument')
                args_num.append(registers[n] & 0xffffffff)
            calls.append({'site':hex(pc),'format_address':hex(registers[1]),
                          'format_bytes_hex':fmt.hex(),'format_arg_count':count,
                          'int_args':args_num})
            # AAPCS64 volatile argument registers cannot survive external calls.
            registers = {}
        else:
            raise ValueError(f'unsupported instruction at {hex(pc)}: {op} {args}')
    if not calls:
        raise ValueError('no recognized libc calls')
    out = ['#include <cstdint>', '#include <cstdio>',
           f'extern "C" void recovered_{entry:x}() {{']
    for i, call in enumerate(calls):
        data = bytes.fromhex(call['format_bytes_hex'])
        out.append(f' static const unsigned char fmt_{i}[] = {{ {_params_ascii(data)} }};')
        params = ', '.join(str(x if x < (1 << 31) else x - (1 << 32))
                           for x in call['int_args'])
        out.append(f' std::printf(reinterpret_cast<const char*>(fmt_{i}){", " + params if params else ""});')
    out.extend(['}', ''])
    return '\n'.join(out), {'entry':hex(entry), 'calls':calls,
        'instructions_translated':len(rows),'source_read':False,'symbols_used':False,
        'read_only_literals_from_elf':True,'abi_assumed':'void()',
        'backend':'EdgeAI static ARM64 subset, no external decompiler',
        'behaviorally_validated':False}


def run(elf, entry):
    scan = analyze(elf)
    if scan['source_read'] or scan['symbols_used']:
        raise ValueError('not symbol/source blind')
    entries = sorted(int(item['address'], 16) for item in scan['candidate_entries'])
    if entry not in entries:
        raise ValueError('must be a stripped-only discovered entry')
    i = entries.index(entry)
    hi = entries[i+1] if i+1 < len(entries) else int(scan['text_address'],16)+scan['text_size_bytes']
    cpp, report = lift(elf, entry, hi)
    report['input_sha256'] = scan['input_sha256']
    return cpp, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--entry', required=True, type=lambda x: int(x, 0))
    p.add_argument('--cpp', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    args = p.parse_args()
    code, evidence = run(args.elf, args.entry)
    args.cpp.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.cpp.write_text(code)
    args.report.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({k:v for k,v in evidence.items() if k != 'calls'}, indent=2))


if __name__ == '__main__':
    main()
