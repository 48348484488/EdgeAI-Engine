#!/usr/bin/env python3
"""Fail-closed, source-blind AArch64 memory-read-only leaf-function C++ lifter.

Input: stripped ELF and candidates discovered from its code bytes. This tool
requires a known pointer-buffer API contract (uint32_t* board, size_t bytes)
and only lowers a deliberately small instruction subset; no function names,
source files, original compilation settings or symbolic oracle are consulted.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
from aarch64_stripped_discovery import analyze

INSTRUCTION = re.compile(r'^\s*([0-9a-fA-F]+):\s+([a-z][a-z0-9.]*)\s*(.*?)\s*$')
REG = re.compile(r'^([wx])([0-9]|[12][0-9]|30)$')
IMM = re.compile(r'^#(0x[0-9a-fA-F]+|[0-9]+)$')
TARGET = re.compile(r'^0x([0-9a-fA-F]+)$')
LOAD = re.compile(r'^(w[0-9]+), \[(x[0-9]+)(?:, (x[0-9]+), lsl #([0-9]+)|, #(0x[0-9a-fA-F]+|[0-9]+))?\]$')
OPSET = {'add','mov','cmp','ldr','b','b.eq','b.ne','b.hi','b.ls','b.ge','b.lt','cbz','cbnz','ret','nop'}


def regvalue(reg):
    m = REG.fullmatch(reg)
    if not m: raise ValueError('unsupported register read '+reg)
    return f'uint32_t(r[{int(m[2])}])' if m[1]=='w' else f'r[{int(m[2])}]'


def regset(reg, value):
    m = REG.fullmatch(reg)
    if not m: raise ValueError('unsupported register write '+reg)
    ctype = 'uint32_t' if m[1]=='w' else 'uint64_t'
    return f'r[{int(m[2])}] = {ctype}({value});'


def operand(x):
    m = IMM.fullmatch(x)
    return str(int(m[1],0))+'ULL' if m else regvalue(x)


def parse_instructions(elf, lo, hi):
    p=subprocess.run(['llvm-objdump','-d','--no-show-raw-insn',f'--start-address={lo}',
                      f'--stop-address={hi}',str(elf)],capture_output=True,text=True,timeout=20,check=True)
    rows=[]
    for line in p.stdout.splitlines():
        m=INSTRUCTION.match(line)
        if m:
            pc,op,args=int(m[1],16),m[2],m[3].split('//',1)[0].strip()
            args=re.sub(r'\s+<[^>]+>$','',args)
            if lo<=pc<hi: rows.append((pc,op,args))
    if len(rows)<2 or len(rows)>4096 or len(rows)*4 != hi-lo or any(row[0]!=lo+i*4 for i,row in enumerate(rows)):
        raise ValueError('cannot cover entire candidate function range with LLVM instructions')
    return rows


def lift(entry,rows,mem_size=64):
    """Emit native C++ for recognized instructions, fail on unsupported effects."""
    pcs={pc for pc,_,_ in rows}
    if entry not in pcs or mem_size < 4 or mem_size > 8192 or mem_size % 4: raise ValueError('invalid selection or memory contract')
    statements=[]; has_ret=False; seen_addressed_load=False
    for pc,op,args in rows:
        operands=[a.strip() for a in args.split(',')] if args else []
        if op not in OPSET: raise ValueError(f'unsupported opcode {pc:#x}: {op} {args}')
        expr=None
        if op=='nop' and args=='': expr=';'
        elif op=='ret' and (not args or args=='x30'):
            expr='return int32_t(uint32_t(r[0]));';has_ret=True
        elif op=='mov' and len(operands)==2:
            if not (IMM.fullmatch(operands[1]) or REG.fullmatch(operands[1])): raise ValueError('bad mov operand')
            expr=regset(operands[0],operand(operands[1]))
        elif op=='add' and len(operands)==3:
            lhs=regvalue(operands[1]);rhs=operand(operands[2]);expr=regset(operands[0],f'{lhs} + {rhs}')
        elif op=='cmp' and len(operands)==2:
            m=REG.fullmatch(operands[0]);rhs=operand(operands[1]);lhs=regvalue(operands[0])
            if not m: raise ValueError('unknown comparison width')
            width=32 if m[1]=='w' else 64
            u=f'uint{width}_t';s=f'int{width}_t'
            expr=(f'{{ {u} a={u}({lhs}),b={u}({rhs}),d=a-b; '
                  f'Z=(d==0); N=({s}(d)<0); C=(a>=b); '
                  f'V=(((a^b)&(a^d))>>{width-1})!=0; }}')
        elif op=='ldr':
            m=LOAD.fullmatch(args)
            if not m: raise ValueError('only bounded 32-bit pointer indexed reads supported: '+args)
            dst,base,idx,shift,imm=m.groups()
            if idx is not None:
                sh=int(shift)
                if sh not in (0,2): raise ValueError('unsupported load scaling')
                addr=f'({regvalue(base)} + ({regvalue(idx)} << {sh}))'
            else:
                addr=f'({regvalue(base)} + {int(imm,0) if imm else 0}ULL)'
            expr=(f'{{ uint64_t addr={addr}; if (addr<origin || addr-origin > {mem_size-4}ULL || (addr-origin)%4ULL) '
                  f'throw std::out_of_range("board read outside contract"); uint32_t word=0; '
                  f'std::memcpy(&word, reinterpret_cast<const void*>(uintptr_t(addr)), 4); '
                  f'{regset(dst,"word")} }}')
            seen_addressed_load=True
        elif op in ('b','b.eq','b.ne','b.hi','b.ls','b.ge','b.lt') and len(operands)==1:
            m=TARGET.fullmatch(operands[0]); dest=int(m[1],16) if m else None
            if dest not in pcs: raise ValueError('branch out of selected candidate, possible tailcall')
            conditions={'b':'true','b.eq':'Z','b.ne':'!Z','b.hi':'C && !Z','b.ls':'!C || Z','b.ge':'N==V','b.lt':'N!=V'}
            expr=f'if ({conditions[op]}) goto pc_{dest:x};'
        elif op in ('cbz','cbnz') and len(operands)==2:
            m=TARGET.fullmatch(operands[1]); dest=int(m[1],16) if m else None
            if dest not in pcs: raise ValueError('conditional branch outside selected range')
            check='==' if op=='cbz' else '!='
            expr=f'if ({regvalue(operands[0])} {check} 0) goto pc_{dest:x};'
        if expr is None: raise ValueError(f'unsupported operand {pc:#x}: {op} {args}')
        statements.append(f'  pc_{pc:x}: if (++steps>1000000ULL) throw std::runtime_error("instruction budget exceeded"); {expr}')
    if not has_ret or not seen_addressed_load: raise ValueError('requires supported returning memory-reader leaf')
    source='\n'.join([
        '#include <cstdint>', '#include <cstring>', '#include <stdexcept>',
        f'extern "C" int32_t recovered_{entry:x}(const uint32_t* input) {{',
        '  if (!input) throw std::invalid_argument("input cannot be null");',
        '  uint64_t r[31] = {}; bool N=false,Z=false,C=false,V=false;',
        '  uint64_t steps=0; uint64_t origin=uint64_t(uintptr_t(input));',
        '  r[0] = origin;'] + statements + ['  throw std::runtime_error("control flow fell through without ret");','}',''])
    return source


def run(elf, entry, mem_size=64):
    scan=analyze(elf)
    if scan['symbols_used'] or scan['source_read']: raise ValueError('source/symbol contamination')
    entries=sorted(int(row['address'],16) for row in scan['candidate_entries'])
    if entry not in entries: raise ValueError('entry must be stripped-only candidate')
    i=entries.index(entry)
    start=int(scan['text_address'],16);end=start+scan['text_size_bytes']
    nxt=entries[i+1] if i+1<len(entries) else end
    if nxt-entry>4096*4 or nxt<=entry: raise ValueError('unsupported function interval')
    rows=parse_instructions(elf,entry,nxt)
    source=lift(entry,rows,mem_size)
    return source,{'status':'LEAF_CPP_LIFTED_NOT_YET_VALIDATED', 'input_sha256':scan['input_sha256'],
        'source_read':False,'symbols_used':False,'entry':hex(entry),'next_candidate':hex(nxt),
        'instructions_translated':len(rows), 'memory_contract_bytes':mem_size,
        'known_abi_assumption':'int32_t function(const uint32_t* buffer)',
        'all_instructions_covered':True,'behavioral_equivalence_proven':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path);p.add_argument('--entry',required=True, type=lambda s:int(s,0))
    p.add_argument('--cpp',required=True,type=Path);p.add_argument('--report',required=True,type=Path)
    a=p.parse_args();cpp,report=run(a.elf,a.entry)
    a.cpp.parent.mkdir(parents=True,exist_ok=True)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.cpp.write_text(cpp);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
