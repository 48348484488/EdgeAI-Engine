#!/usr/bin/env python3
"""Strict ELF-only AArch64 to C++ lifter for a three-argument board/score leaf.

Declared ABI: uint32_t f(uint32_t board[16], uint8_t column, uint32_t* score).
This is a testing assumption, not an automatically recovered original type.
Reads ONLY LLVM disassembly of a stripped ELF; all unsupported ops fail.
"""
import argparse
import json
from pathlib import Path
import re
from aarch64_stripped_discovery import analyze
from aarch64_leaf_lifter import parse_instructions, regvalue, regset, operand, REG, TARGET

ALLOWED = {'mov','and','ubfiz','sbfiz','add','lsl','ldr','str',
           'cmp','cmn','csetm','b','b.eq','b.ne','cbz','cbnz','ret'}
MEM = re.compile(r'^(w(?:[12]?\d|30|zr)), \[(x(?:[12]?\d|30))(?:, (x(?:[12]?\d|30))(?:, lsl #(\d+))?|, #(0x[0-9a-fA-F]+|\d+))?\]$')


def _loadstore(op,args):
    m=MEM.fullmatch(args)
    if m is None:raise ValueError('unrecognized bounded memory access '+args)
    reg,base,index,shift,off=m.groups()
    if index:
        bits=int(shift) if shift else 0
        if bits not in (0,2):raise ValueError('unsupported index scale')
        addr=f'({regvalue(base)} + ({regvalue(index)} << {bits}))'
    else:
        addr=f'({regvalue(base)} + {int(off,0) if off else 0}ULL)'
    if op=='ldr' and reg=='wzr':raise ValueError('unsupported load into zero register')
    stmt=f'uint64_t address={addr}; check_addr(address); '
    if op=='ldr':
        stmt+=f'uint32_t word=0; std::memcpy(&word, reinterpret_cast<const void*>(uintptr_t(address)), 4); {regset(reg,"word")}'
    else:
        value='0U' if reg=='wzr' else regvalue(reg)
        stmt+=f'uint32_t word=uint32_t({value}); std::memcpy(reinterpret_cast<void*>(uintptr_t(address)), &word, 4);'
    return '{ '+stmt+' }'


def _flags(op,a,b):
    m=REG.fullmatch(a)
    if not m:raise ValueError('invalid NZCV operand '+a)
    bits=32 if m[1]=='w' else 64
    tp=f'uint{bits}_t'
    left,right=regvalue(a),operand(b)
    if op=='cmp':
        return (f'{{ {tp} aa={tp}({left}),bb={tp}({right}),dd=aa-bb; '
                f'Z=dd==0;N=((dd>>{bits-1})&1)!=0;C=aa>=bb; '
                f'V=(((aa^bb)&(aa^dd))>>{bits-1})!=0; }}')
    return (f'{{ {tp} aa={tp}({left}),bb={tp}({right}),dd=aa+bb; '
            f'Z=dd==0;N=((dd>>{bits-1})&1)!=0;C=dd<aa; '
            f'V=(((~(aa^bb))&(aa^dd))>>{bits-1})!=0; }}')


def lift(entry,rows):
    pcs={pc for pc,_,_ in rows}
    if not (2<=len(rows)<=1024 and len(rows)==len(pcs) and
            rows[0][0]==entry and all(pc==entry+4*i for i,(pc,_,_) in enumerate(rows))):
        raise ValueError('noncontiguous or oversized instructions')
    statements=[]
    op_counts={}
    have_read=have_write=have_ret=False
    for pc,op,args in rows:
        if op not in ALLOWED:raise ValueError(f'unsupported opcode {pc:#x}: {op} {args}')
        op_counts[op]=op_counts.get(op,0)+1
        parts=[x.strip() for x in args.split(',')] if args else []
        stmt=None
        if op=='ret' and args in ('','x30'):
            stmt='return uint32_t(r[0]);';have_ret=True
        elif op=='mov' and len(parts)==2:
            stmt=regset(parts[0],operand(parts[1]))
        elif op=='and' and len(parts)==3:
            stmt=regset(parts[0],f'{regvalue(parts[1])} & {operand(parts[2])}')
        elif op=='ubfiz' and len(parts)==4:
            shift=int(parts[2].lstrip('#'),0);width=int(parts[3].lstrip('#'),0)
            if not 0<width<=32 or not 0<=shift<=32 or shift+width>64:
                raise ValueError('unsupported bitfield layout')
            stmt=regset(parts[0],f'(({regvalue(parts[1])} & {((1<<width)-1)}ULL) << {shift})')
        elif op=='sbfiz' and len(parts)==4:
            shift=int(parts[2].lstrip('#'),0);width=int(parts[3].lstrip('#'),0)
            if width!=32 or not 0<=shift<32:raise ValueError('unsupported signed bitfield layout')
            stmt=regset(parts[0],f'(uint64_t(int64_t(int32_t(uint32_t({regvalue(parts[1])})))) << {shift})')
        elif op=='lsl' and len(parts)==3:
            shift=int(parts[2].lstrip('#'),0)
            if not 0<=shift<32:raise ValueError('shift out of range')
            stmt=regset(parts[0],f'{regvalue(parts[1])} << {shift}')
        elif op=='add' and len(parts) in (3,4):
            if len(parts)==4:
                if parts[3]!='sxtw #2' or not re.fullmatch(r'w(?:[12]?\d|30)',parts[2]):
                    raise ValueError('unsupported extended arithmetic '+args)
                rhs=f'(uint64_t(int64_t(int32_t(uint32_t({regvalue(parts[2])})))) << 2)'
            else:rhs=operand(parts[2])
            stmt=regset(parts[0],f'{regvalue(parts[1])} + {rhs}')
        elif op in ('cmp','cmn') and len(parts)==2:
            stmt=_flags(op,parts[0],parts[1])
        elif op=='csetm' and len(parts)==2:
            if parts[1] not in ('eq','ne'):raise ValueError('unsupported csetm condition')
            cond='Z' if parts[1]=='eq' else '!Z'
            stmt=regset(parts[0],f'({cond} ? 0xffffffffffffffffULL : 0ULL)')
        elif op in ('ldr','str'):
            stmt=_loadstore(op,args)
            have_read |= op=='ldr';have_write |= op=='str'
        elif op in ('b','b.eq','b.ne') and len(parts)==1:
            m=TARGET.fullmatch(parts[0]);target=int(m[1],16) if m else None
            if target not in pcs:raise ValueError('branch outside function candidate')
            cond={'b':'true','b.eq':'Z','b.ne':'!Z'}[op]
            stmt=f'if ({cond}) goto pc_{target:x};'
        elif op in ('cbz','cbnz') and len(parts)==2:
            m=TARGET.fullmatch(parts[1]);target=int(m[1],16) if m else None
            if target not in pcs:raise ValueError('branch outside function')
            stmt=f'if ({regvalue(parts[0])} {"==" if op=="cbz" else "!="} 0) goto pc_{target:x};'
        if stmt is None:raise ValueError(f'unsupported operands {pc:#x}: {op} {args}')
        statements.append(f' pc_{pc:x}: if(++budget>1000000ULL) throw std::runtime_error("instruction budget"); {stmt}')
    if not all((have_read,have_write,have_ret)):
        raise ValueError('requires memory reads, writes, and return')
    code='\n'.join([
        '#include <cstdint>','#include <cstring>','#include <stdexcept>',
        f'extern "C" uint32_t recovered_{entry:x}(uint32_t* board,uint32_t column,uint32_t* score) {{',
        ' if (!board || !score || column>3) throw std::invalid_argument("invalid board/score/column");',
        ' uint64_t r[31]={}; bool Z=false,N=false,C=false,V=false; uint64_t budget=0;',
        ' uint64_t origin=uint64_t(uintptr_t(board)); uint64_t score_addr=uint64_t(uintptr_t(score));',
        ' auto check_addr=[&](uint64_t addr){',
        '  bool board_ok=addr>=origin && addr-origin<=60 && ((addr-origin)&3)==0;',
        '  bool score_ok=addr==score_addr;',
        '  if(!board_ok && !score_ok)throw std::out_of_range("board/score address");',
        ' };',
        ' r[0]=origin; r[1]=column; r[2]=score_addr;',
        *statements,
        ' throw std::runtime_error("fell through function");','}',''])
    return code,op_counts


def run(elf,entry):
    scan=analyze(elf)
    if scan['symbols_used'] or scan['source_read']:raise ValueError('not stripped source-blind input')
    entries=sorted(int(x['address'],16) for x in scan['candidate_entries'])
    if entry not in entries:raise ValueError('start not discovered in stripped ELF')
    i=entries.index(entry)
    hi=entries[i+1] if i+1<len(entries) else int(scan['text_address'],16)+scan['text_size_bytes']
    if not entry<hi<=entry+4096:raise ValueError('unsafe candidate size')
    rows=parse_instructions(elf,entry,hi)
    source,op_counts=lift(entry,rows)
    return source,{'status':'CPP_EMITTED_UNVALIDATED','source_read':False,'symbols_used':False,
        'entry':hex(entry),'next_candidate':hex(hi),'input_sha256':scan['input_sha256'],
        'instructions_translated':len(rows),'opcodes':op_counts,
        'ABI_assumption':'uint32_t f(uint32_t board[16],uint8_t column,uint32_t* score)',
        'behavioral_equivalence_proven':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--entry',required=True,type=lambda x:int(x,0))
    p.add_argument('--cpp',required=True,type=Path)
    p.add_argument('--report',required=True,type=Path)
    a=p.parse_args();source,report=run(a.elf,a.entry)
    a.cpp.parent.mkdir(parents=True,exist_ok=True);a.report.parent.mkdir(parents=True,exist_ok=True)
    a.cpp.write_text(source);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
