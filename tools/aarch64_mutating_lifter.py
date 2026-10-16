#!/usr/bin/env python3
"""Emit source-blind C++ for a bounded ARM64 array-mutating leaf.

Only decodes an explicitly supported subset of ARM64, with register arithmetic,
flags, CFG branches and 32-bit load/store including indexed and pre-indexed
addressing. The recovered entry signature is an external ABI assumption:
void f(uint32_t board[16]); this tool does not recover original prototypes.

No original game source or ELF symbol table is read by this module.
"""
import argparse
import json
from pathlib import Path
import re

from aarch64_leaf_lifter import parse_instructions, regvalue, regset, operand, REG, TARGET
from aarch64_stripped_discovery import analyze

ACCESS = re.compile(r'^(w(?:[12]?\d|30|zr)),\s*\[(x(?:[12]?\d|30))(?:,\s*(x(?:[12]?\d|30)),\s*lsl\s*#(\d+)|,\s*#(0x[0-9a-fA-F]+|\d+))?\](!?)$')
OPS = frozenset({'add', 'mov', 'cmp', 'and', 'ldr', 'str', 'b', 'b.eq',
                 'b.ne', 'b.hi', 'b.ls', 'b.ge', 'b.lt', 'cbz', 'cbnz', 'ret', 'nop'})


def _memory_access(op, args, size=64):
    m = ACCESS.fullmatch(args)
    if m is None:
        raise ValueError(f'unsupported memory operand: {op} {args}')
    reg, base, idx, shift, immediate, writeback = m.groups()
    if reg == 'wzr' and op == 'ldr':
        raise ValueError('wzr load not supported')
    if idx is not None:
        if writeback:
            raise ValueError('register-indexed pre-indexed addressing unsupported')
        sh = int(shift)
        if sh not in (0, 2):
            raise ValueError('unsupported register offset scaling')
        address = f'({regvalue(base)} + ({regvalue(idx)} << {sh}))'
    else:
        off = int(immediate, 0) if immediate else 0
        if not 0 <= off <= size:
            raise ValueError('immediate memory offset outside contract')
        address = f'({regvalue(base)} + {off}ULL)'
    guard = (f'uint64_t addr = {address}; '
             f'if (addr < origin || addr-origin > {size-4}ULL || ((addr-origin)&3ULL)) '
             'throw std::out_of_range("board access outside contract"); ')
    if op == 'ldr':
        load = ('uint32_t word=0; '
                'std::memcpy(&word, reinterpret_cast<const void*>(uintptr_t(addr)), 4); '
                + regset(reg, 'word'))
    else:
        v = '0U' if reg == 'wzr' else regvalue(reg)
        load = ('uint32_t word=uint32_t(' + v + '); '
                'std::memcpy(reinterpret_cast<void*>(uintptr_t(addr)), &word, 4); ')
    if writeback:
        load += regset(base, 'addr')
    return '{ ' + guard + load + ' }'


def lift_mutator(entry, rows, mem_size=64):
    if not 4 <= mem_size <= 8192 or mem_size % 4:
        raise ValueError('memory contract outside supported range')
    pcs = {pc for pc, _, _ in rows}
    if entry not in pcs or len(pcs) != len(rows):
        raise ValueError('entry or duplicated instruction PC')
    if not 2 <= len(rows) <= 4096 or any(pc!=entry+4*i for i,(pc,_,_) in enumerate(rows)):
        raise ValueError('incomplete/nonlinear function listing')
    statements = []
    has_ret = has_load = has_store = False
    for pc, op, args in rows:
        if op not in OPS:
            raise ValueError(f'unsupported ARM64 opcode {pc:#x}: {op} {args}')
        operands = [x.strip() for x in args.split(',')] if args else []
        stmt = None
        if op == 'nop' and not args:
            stmt = ';'
        elif op == 'ret' and args in ('', 'x30'):
            stmt = 'return;';has_ret=True
        elif op == 'mov' and len(operands)==2:
            stmt = regset(operands[0], operand(operands[1]))
        elif op in ('add','and') and len(operands)==3:
            lhs, rhs = regvalue(operands[1]), operand(operands[2])
            stmt = regset(operands[0],f'{lhs} {"+" if op=="add" else "&"} {rhs}')
        elif op == 'cmp' and len(operands)==2:
            m=REG.fullmatch(operands[0]); lhs=regvalue(operands[0]);rhs=operand(operands[1])
            if not m:
                raise ValueError('unknown comparison width')
            width=32 if m[1]=='w' else 64
            u=f'uint{width}_t'
            stmt=(f'{{ {u} a={u}({lhs}),b={u}({rhs}),d=a-b; '
                  f'Z=(d==0); N=((d>>{width-1})&1)!=0; C=(a>=b); '
                  f'V=(((a^b)&(a^d))>>{width-1})!=0; }}')
        elif op in ('ldr','str'):
            stmt=_memory_access(op,args,mem_size)
            has_load |= op=='ldr';has_store |= op=='str'
        elif op in ('b','b.eq','b.ne','b.hi','b.ls','b.ge','b.lt') and len(operands)==1:
            m=TARGET.fullmatch(operands[0]);dest=int(m[1],16) if m else None
            if dest not in pcs:
                raise ValueError('branch outside selected candidate')
            cond={'b':'true','b.eq':'Z','b.ne':'!Z','b.hi':'C && !Z',
                  'b.ls':'!C || Z','b.ge':'N==V','b.lt':'N!=V'}[op]
            stmt=f'if ({cond}) goto pc_{dest:x};'
        elif op in ('cbz','cbnz') and len(operands)==2:
            m=TARGET.fullmatch(operands[1]);dest=int(m[1],16) if m else None
            if dest not in pcs:
                raise ValueError('branch outside selected candidate')
            stmt=f'if ({regvalue(operands[0])} {"==" if op=="cbz" else "!="} 0) goto pc_{dest:x};'
        if stmt is None:
            raise ValueError(f'unsupported operands {pc:#x}: {op} {args}')
        statements.append(f'  pc_{pc:x}: if (++steps>1000000ULL) throw std::runtime_error("instruction budget exceeded"); {stmt}')
    if not (has_ret and has_load and has_store):
        raise ValueError('need read, write and return on this mutating function')
    return '\n'.join([
        '#include <cstdint>', '#include <cstring>', '#include <stdexcept>',
        f'extern "C" void recovered_{entry:x}(uint32_t* input) {{',
        '  if (!input) throw std::invalid_argument("input must be nonnull");',
        '  uint64_t r[31] = {}; bool N=false,Z=false,C=false,V=false;',
        '  uint64_t steps=0; uint64_t origin=uint64_t(uintptr_t(input));',
        '  r[0] = origin;',
        *statements,
        '  throw std::runtime_error("control flow fell through without ret");', '}', ''])


def run(elf, entry, mem_size=64):
    scan=analyze(elf)
    if scan['symbols_used'] or scan['source_read']:
        raise ValueError('blind input contract not met')
    entries=sorted(int(row['address'],16) for row in scan['candidate_entries'])
    if entry not in entries:
        raise ValueError('start must be discovered from stripped ELF')
    idx=entries.index(entry)
    stop=entries[idx+1] if idx+1<len(entries) else int(scan['text_address'],16)+scan['text_size_bytes']
    if stop<=entry or stop-entry>16384:
        raise ValueError('uncertain bounded function size')
    rows=parse_instructions(elf, entry, stop)
    code=lift_mutator(entry,rows,mem_size)
    return code, {
        'status':'MUTATING_CPP_LIFTED_NOT_YET_BEHAVIORALLY_VALIDATED',
        'entry':hex(entry),'next_candidate':hex(stop),'instruction_count':len(rows),
        'input_sha256':scan['input_sha256'],'source_read':False,'symbols_used':False,
        'memory_contract_bytes':mem_size,'return_abi_assumption':'void(uint32_t*)',
        'behaviorally_validated':False,'whole_game_decompiled':False,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--entry',required=True,type=lambda x:int(x,0))
    p.add_argument('--cpp',required=True,type=Path)
    p.add_argument('--report',required=True,type=Path)
    a=p.parse_args()
    cpp,report=run(a.elf,a.entry)
    a.cpp.parent.mkdir(parents=True,exist_ok=True)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.cpp.write_text(cpp,encoding='utf-8')
    a.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
