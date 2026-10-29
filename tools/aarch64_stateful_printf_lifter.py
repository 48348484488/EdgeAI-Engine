#!/usr/bin/env python3
"""Bounded source-blind AArch64 global-u32/printf/snprintf -> C++ lifter.

Accepts only a single zero-initialized 32-bit .bss slot, a balanced frame,
conditional branches, and known fortified libc calls. Does not read source or
ELF .symtab. Generated code is NOT behaviorally validated by this tool.
"""
import argparse
import json
from pathlib import Path
import re
import struct

from aarch64_leaf_lifter import parse_instructions
from aarch64_printf_lifter import load_rodata, plt_symbols
from aarch64_static_printf_sequence_lifter import printf_items
from aarch64_stripped_discovery import analyze
from aarch64_branch_printf_lifter import (_bounded_frame, _parts, _read, _write,
                                          _reg, IMM, TARG, _literal)

MEM = re.compile(r'^(w(?:[0-9]|[12][0-9]|30)), \[(x(?:[0-9]|[12][0-9]|30)), #(0x[0-9a-fA-F]+|[0-9]+)\]$')
PAIR = re.compile(r'^(x(?:[12]?\d|30)), (x(?:[12]?\d|30)), \[sp, #(0x[0-9a-fA-F]+|[0-9]+)\]$')


def _bss_region(elf):
    data = Path(elf).read_bytes()
    if data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('requires little-endian ELF64')
    h = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    if h[1] != 183 or h[2] != 1 or not 1 <= h[11] <= 4096 or h[10] < 64:
        raise ValueError('requires AArch64 ELF sections')
    shoff, entsize, count, names_index = h[5], h[10], h[11], h[12]
    if names_index >= count or shoff + entsize * count > len(data):
        raise ValueError('ELF section headers outside file')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + i * entsize)
                for i in range(count)]
    ns = sections[names_index]
    if ns[4] + ns[5] > len(data):
        raise ValueError('ELF section names outside file')
    names = data[ns[4]:ns[4] + ns[5]]
    bss = []
    for sec in sections:
        nameoff, typ, flags, addr, off, size, *_ = sec
        if nameoff >= len(names):
            raise ValueError('invalid ELF section name')
        if names[nameoff:].split(b'\x00', 1)[0] == b'.bss':
            if typ != 8 or flags & 3 != 3 or flags & 4 or size < 4 or size > 1 << 20:
                raise ValueError('invalid writable zero-initialized section')
            bss.append((addr, size))
    if len(bss) != 1:
        raise ValueError('requires exactly one .bss')
    return bss[0]


def _single_global_slot(rows, bss):
    """Prove one STR32 destination from a local ADRP+immediate address chain."""
    candidates = []
    for i, (pc, op, args) in enumerate(rows):
        if op != 'str' or not (m := MEM.fullmatch(args)):
            continue
        _, base, off = m.groups()
        for j in range(i-1, max(-1, i-5), -1):
            _, prior, pargs = rows[j]
            q = _parts(pargs)
            if q and q[0] == base:
                if prior != 'adrp' or len(q) != 2 or not TARG.fullmatch(q[1]):
                    raise ValueError('global STR base not directly proven by ADRP')
                address = int(q[1], 0) + int(off, 0)
                candidates.append(address)
                break
        else:
            raise ValueError('cannot prove global STR base')
    if len(candidates) != 1:
        raise ValueError('requires one statically proved global store site')
    address = candidates[0]
    start, size = bss
    if address % 4 or not start <= address <= start + size - 4:
        raise ValueError('global state slot outside aligned .bss')
    return address


def _formats(rodata):
    base, data = rodata
    printf_cases = []
    snprintf_cases = []
    for i, byte in enumerate(data):
        if i and data[i-1] != 0:
            continue
        end = data.find(b'\0', i)
        if end < 0 or end - i > 1024:
            continue
        fmt = data[i:end]
        try:
            roles = printf_items(fmt.replace(b'%*d', b'%d%d'))
        except (ValueError, UnicodeDecodeError):
            continue
        if roles == []:
            printf_cases.append((base+i, []))
        elif roles == ['int']:
            printf_cases.append((base+i, ['int']))
            if re.fullmatch(rb'[^%]*(?:%%[^%]*)*%[-+ 0#]*\d{0,3}(?:\.\d{1,3})?d[^%]*', fmt):
                snprintf_cases.append(base+i)
        elif roles == ['int', 'int']:
            printf_cases.append((base+i, ['int','int']))
    return printf_cases, snprintf_cases


def lift(elf, entry, stop):
    rows = parse_instructions(elf, entry, stop)
    if not 20 <= len(rows) <= 256:
        raise ValueError('not a bounded stateful printer')
    frame, saved, epilogue = _bounded_frame(rows)
    if (epilogue+4,'ret','') not in rows or sum(op=='ret' for _,op,_ in rows)!=1:
        raise ValueError('requires a single balanced return')
    bss = _bss_region(elf)
    state_addr = _single_global_slot(rows, bss)
    plt = plt_symbols(elf)
    if '__printf_chk' not in plt.values() or '__snprintf_chk' not in plt.values():
        raise ValueError('required dynamic imports missing')
    rodata = load_rodata(elf)
    formats, snprintf_formats = _formats(rodata)
    if not formats or not snprintf_formats:
        raise ValueError('no supported ELF format strings')
    valid = {pc for pc, _, _ in rows}
    base, data = rodata
    code = [
        '#include <cstdint>', '#include <cstdio>', '#include <cstring>', '#include <stdexcept>',
        f'extern "C" void recovered_{entry:x}(uint32_t arg0) {{',
        f' static uint32_t global_u32 = 0; // zero-initialized .bss slot recovered from ELF',
        f' constexpr uint64_t STATE_ADDR={state_addr}ULL;',
        f' static const unsigned char rodata[] = {{{_literal(data)}}};',
        f' constexpr uint64_t RODATA_BASE={base}ULL, RODATA_END={base+len(data)}ULL;',
        ' uint64_t r[31]={}; bool N=false,Z=false,C=false,V=false;',
        ' uint64_t budget=0; r[0]=arg0;',
        ' auto get_fmt=[&](uint64_t addr)->const char* {',
        '   if(addr<RODATA_BASE || addr>=RODATA_END) throw std::runtime_error("format outside .rodata");',
        '   const unsigned char *p=rodata+(addr-RODATA_BASE);',
        '   if(!std::memchr(p,0,RODATA_END-addr)) throw std::runtime_error("unterminated format");',
        '   return reinterpret_cast<const char*>(p);',
        ' };',
        ' auto read_global=[&](uint64_t addr)->uint32_t {',
        '   if(addr!=STATE_ADDR)throw std::runtime_error("unproved global load");',
        '   return global_u32;',
        ' };',
        ' auto write_global=[&](uint64_t addr,uint32_t value) {',
        '   if(addr!=STATE_ADDR)throw std::runtime_error("unproved global store");',
        '   global_u32=value;',
        ' };',
        ' auto checked_printf=[&]()->int {',
        '   if(uint32_t(r[0])!=2)throw std::runtime_error("invalid printf fortify flag");',
        '   const char*fmt=get_fmt(r[1]);',
        '   switch(r[1]) {',
    ]
    for addr, roles in formats:
        params = ','.join(f'int32_t(uint32_t(r[{i}]))' for i in range(2,2+len(roles)))
        code.append(f'    case {addr}ULL: return std::printf(fmt{","+params if params else ""});')
    code.extend(['    default:throw std::runtime_error("unapproved printf format");', '   }',' };',
        ' auto checked_snprintf=[&]()->int {',
        '   if(r[0]!=0 || r[1]!=0 || uint32_t(r[2])!=2 || r[3]!=UINT64_MAX)',
        '     throw std::runtime_error("unsupported fortified snprintf ABI");',
        '   const char*fmt=get_fmt(r[4]);',
        '   switch(r[4]) {'])
    for addr in snprintf_formats:
        code.append(f'    case {addr}ULL: return std::snprintf(nullptr,0,fmt,int32_t(uint32_t(r[5])));')
    code.extend(['    default:throw std::runtime_error("unapproved snprintf format");','   }',' };'])
    sites={'printf':0,'snprintf':0,'load':0,'store':0}
    for pc, op, args in rows:
        p = _parts(args)
        expr = None
        if pc in (rows[0][0], rows[1][0], epilogue):
            expr = ';'
        elif op in ('stp','ldp'):
            if not PAIR.fullmatch(args):
                raise ValueError('unverified register pair save/restore')
            expr = ';'
        elif op == 'ret' and args in ('','x30'):
            expr = 'return;'
        elif op == 'mov' and len(p) == 2:
            expr = _write(p[0], _read(p[1]))
        elif op == 'adrp' and len(p) == 2 and TARG.fullmatch(p[1]):
            if p[0][0] != 'x' or int(p[1],0)%4096:
                raise ValueError('invalid ADRP page')
            expr = _write(p[0], str(int(p[1],0))+'ULL')
        elif op in ('add','sub') and len(p) == 3:
            expr = _write(p[0],f'({_read(p[1])}{"+" if op=="add" else "-"}{_read(p[2])})')
        elif op in ('ldr','str') and (m := MEM.fullmatch(args)):
            reg, base_reg, off = m.groups()
            address = f'({_read(base_reg)}+{int(off,0)}ULL)'
            if op == 'ldr':
                expr = _write(reg, f'read_global({address})'); sites['load']+=1
            else:
                expr = f'write_global({address},uint32_t({_read(reg)}));'; sites['store']+=1
        elif op == 'cmp' and len(p) == 2:
            _, width = _reg(p[0]); u = 'uint32_t' if width=='w' else 'uint64_t'; sh=31 if width=='w' else 63
            expr = (f'{{ {u} a={u}({_read(p[0])}),b={u}({_read(p[1])}),d={u}(a-b);'
                    f' Z=(d==0);N=bool((d>>{sh})&1);C=(a>=b);V=bool(((a^b)&(a^d))>>{sh}); }}')
        elif op in ('b','b.eq','b.ne') and len(p)==1:
            target = int(p[0],0) if TARG.fullmatch(p[0]) else -1
            if target not in valid: raise ValueError('branch target outside candidate')
            cond = {'b':'true','b.eq':'Z','b.ne':'!Z'}[op]
            expr = f'if({cond})goto pc_{target:x};'
        elif op=='bl' and len(p)==1 and TARG.fullmatch(p[0]):
            imported = plt.get(int(p[0],0))
            if imported=='__printf_chk':
                expr = 'r[0]=uint32_t(checked_printf());'; sites['printf']+=1
            elif imported=='__snprintf_chk':
                expr = 'r[0]=uint32_t(checked_snprintf());'; sites['snprintf']+=1
            else: raise ValueError('unrecognized call target')
        if expr is None: raise ValueError(f'unsupported opcode {hex(pc)}: {op} {args}')
        code.append(f' pc_{pc:x}: if(++budget>10000)throw std::runtime_error("instruction budget"); {expr}')
    if sites['printf']<3 or sites['snprintf']!=1 or sites['load']<2 or sites['store']!=1:
        raise ValueError('not a single-state formatted printer')
    code.extend([' throw std::runtime_error("fallthrough without return");','}',''])
    return '\n'.join(code), {
        'address':hex(entry), 'instructions_translated':len(rows),
        'global_state_address':hex(state_addr),'global_state_section':'.bss',
        'printf_call_sites':sites['printf'],'snprintf_call_sites':sites['snprintf'],
        'global_load_sites':sites['load'],'global_store_sites':sites['store'],
        'frame_bytes':frame,'preserved_reg_pairs':saved,
        'ABI_assumption':'void(uint32_t)','source_read':False,'symbols_used':False,
        'behaviorally_validated':False
    }


def discover(elf):
    scan = analyze(elf)
    if scan['source_read'] is not False or scan['symbols_used'] is not False:
        raise ValueError('requires source-blind discovery')
    entries = sorted(int(x['address'],16) for x in scan['candidate_entries'])
    end = int(scan['text_address'],16) + scan['text_size_bytes']
    found=[]; rejected={}
    for i,entry in enumerate(entries):
        try:
            source,meta=lift(elf,entry,entries[i+1] if i+1<len(entries) else end)
            found.append((entry,source,meta))
        except (ValueError,KeyError,RuntimeError) as exc:
            rejected[hex(entry)]=str(exc)
    return found,rejected


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    found,rejected=discover(args.elf)
    if not found:raise ValueError('no stateful printer matched')
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for entry,src,meta in found:
        (args.output_dir/f'candidate_{entry:x}.cpp').write_text(src)
    (args.output_dir/'stateful_coverage.json').write_text(json.dumps({
        'matches':[x[2] for x in found],'rejected':rejected},indent=2)+'\n')
    print(json.dumps({'matches':[x[2] for x in found],'rejected_count':len(rejected)},indent=2))

if __name__=='__main__':main()
