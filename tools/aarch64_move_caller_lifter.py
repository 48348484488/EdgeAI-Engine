#!/usr/bin/env python3
"""Stripped AArch64 to C++ interprocedural translator for board/score callers.

Only accepts a balanced recognized AAPCS64 paired-register stack frame,
register operations and BL to previously lifted functions with *declared*
ABI contracts. Callee roles must come from a matching input-ELF manifest.
Never consults original C, symbol names or external decompiler output.
"""
import argparse
import json
from pathlib import Path
import re
from aarch64_leaf_lifter import parse_instructions, regvalue, regset, operand, REG, TARGET
from aarch64_stripped_discovery import analyze

PAIR = re.compile(r'^(x(?:[12]?\d|30)), (x(?:[12]?\d|30)), \[sp, #(-?0x[0-9a-fA-F]+)\](!?)$')
POST = re.compile(r'^(x(?:[12]?\d|30)), (x(?:[12]?\d|30)), \[sp\], #(0x[0-9a-fA-F]+)$')
OPS = {'stp','ldp','mov','bl','and','orr','add','cmp','b','b.eq','b.ne','ret'}
ABI = {'board_only_mutator','board_column_score_leaf','board_score_caller'}


def _verify_frame(rows):
    if len(rows)<8:raise ValueError('insufficient body')
    if rows[0][1]!='stp':raise ValueError('no saved frame prologue')
    m=PAIR.fullmatch(rows[0][2])
    if not m or m.group(1,2)!=('x29','x30') or m[4]!='!':
        raise ValueError('unsupported frame opening')
    frame_size=-int(m[3],0)
    if frame_size not in (0x20,0x30,0x40):
        raise ValueError('unbounded frame size')
    if rows[1][1:]!=('mov','x29, sp'):
        raise ValueError('unexpected FP setup')
    saves=[];restores=[];ending=0
    for _,op,args in rows:
        if op=='stp':
            a=PAIR.fullmatch(args)
            if not a:raise ValueError('unsupported stack store')
            saves.append((a[1],a[2],a[3],a[4]))
        elif op=='ldp':
            a=PAIR.fullmatch(args)
            if a:restores.append((a[1],a[2],a[3],a[4]))
            else:
                a=POST.fullmatch(args)
                if a and a.group(1,2)==('x29','x30') and int(a[3],0)==frame_size:
                    ending+=1
                else:raise ValueError('unsupported frame restore')
    if ending!=1 or rows[-2][1:]!=('ldp',f'x29, x30, [sp], #{hex(frame_size)}') or rows[-1][1:]!=('ret',''):
        raise ValueError('invalid paired frame closure')
    if len(saves)!=len(restores)+1 or len(set(saves))!=len(saves):
        raise ValueError('save/restore count mismatch')
    for saved in saves[1:]:
        if saved not in restores or restores.count(saved)!=1:
            raise ValueError('unbalanced preserved register pair')
        off=int(saved[2],0)
        if off<0x10 or off+16>frame_size:
            raise ValueError('save outside frame')
    return frame_size


def _declaration(entry,kind):
    if kind=='board_only_mutator':return f'extern "C" void recovered_{entry:x}(uint32_t*);'
    if kind=='board_column_score_leaf':
        return f'extern "C" uint32_t recovered_{entry:x}(uint32_t*,uint32_t,uint32_t*);'
    if kind=='board_score_caller':
        return f'extern "C" uint32_t recovered_{entry:x}(uint32_t*,uint32_t*);'
    raise ValueError('unsupported callee ABI')


def lift(entry,rows,contract):
    if len(rows)>256 or not rows or rows[0][0]!=entry or any(pc!=entry+4*i for i,(pc,_,_) in enumerate(rows)):
        raise ValueError('invalid function bounds')
    _verify_frame(rows)
    pcs={pc for pc,_,_ in rows}
    statements=[];called=set();has_ret=False
    for pc,op,args in rows:
        if op not in OPS:raise ValueError(f'unsupported ARM64 opcode {pc:#x}: {op} {args}')
        parts=[p.strip() for p in args.split(',')] if args else []
        stmt=None
        if op in ('stp','ldp'):
            stmt='; /* checked balanced stack-frame effect */'
        elif op=='mov' and args=='x29, sp':
            stmt='; /* validated frame pointer initialization */'
        elif op=='mov' and len(parts)==2:
            stmt=regset(parts[0],operand(parts[1]))
        elif op in ('and','orr','add') and len(parts)==3:
            symbol={'and':'&','orr':'|','add':'+'}[op]
            stmt=regset(parts[0],f'{regvalue(parts[1])} {symbol} {operand(parts[2])}')
        elif op=='cmp' and len(parts)==2:
            m=REG.fullmatch(parts[0])
            width=32 if m and m[1]=='w' else 64 if m else None
            if width is None:raise ValueError('bad compare')
            typ=f'uint{width}_t'
            aa=regvalue(parts[0]);bb=operand(parts[1])
            stmt=(f'{{ {typ} a={typ}({aa}),b={typ}({bb}),d=a-b; '
                  f'Z=(d==0);N=((d>>{width-1})&1)!=0;C=a>=b;'
                  f'V=(((a^b)&(a^d))>>{width-1})!=0; }}')
        elif op in ('b','b.eq','b.ne') and len(parts)==1:
            m=TARGET.fullmatch(parts[0]);dest=int(m[1],16) if m else None
            if dest not in pcs:raise ValueError('unresolved local branch')
            cond={'b':'true','b.eq':'Z','b.ne':'!Z'}[op]
            stmt=f'if ({cond}) goto pc_{dest:x};'
        elif op=='bl' and len(parts)==1:
            m=TARGET.fullmatch(parts[0]);dest=int(m[1],16) if m else None
            kind=contract.get(dest)
            if kind not in ABI:
                raise ValueError(f'BL target {dest} lacks tested ABI and C++ module')
            called.add((dest,kind))
            if kind=='board_only_mutator':
                call=f'recovered_{dest:x}(reinterpret_cast<uint32_t*>(uintptr_t(r[0]))); r[0]=0;'
            elif kind=='board_column_score_leaf':
                call=f'r[0]=recovered_{dest:x}(reinterpret_cast<uint32_t*>(uintptr_t(r[0])),uint32_t(r[1]),reinterpret_cast<uint32_t*>(uintptr_t(r[2])));'
            else:
                call=f'r[0]=recovered_{dest:x}(reinterpret_cast<uint32_t*>(uintptr_t(r[0])),reinterpret_cast<uint32_t*>(uintptr_t(r[1])));'
            # Unspecified AAPCS64 caller-saved registers, except w0 return.
            stmt='{ '+call+' for(unsigned j=1;j<=18;j++)r[j]=0; }'
        elif op=='ret' and args=='':
            stmt='return uint32_t(r[0]);';has_ret=True
        if stmt is None:
            raise ValueError(f'unsupported instruction form {pc:#x}: {op} {args}')
        statements.append(f' pc_{pc:x}: if(++budget>1000000ULL) throw std::runtime_error("instruction budget"); {stmt}')
    if not (has_ret and called):
        raise ValueError('missing return or verified BL')
    declarations=[_declaration(addr,kind) for addr,kind in sorted(called)]
    cpp='\n'.join(['#include <cstdint>','#include <stdexcept>',*declarations,
        f'extern "C" uint32_t recovered_{entry:x}(uint32_t* board, uint32_t* score) {{',
        ' if(!board || !score)throw std::invalid_argument("null ABI pointer");',
        ' uint64_t r[31]={}; bool N=false,Z=false,C=false,V=false; uint64_t budget=0;',
        ' r[0]=uint64_t(uintptr_t(board));r[1]=uint64_t(uintptr_t(score));',
        *statements,' throw std::runtime_error("missing return");','}',''])
    return cpp,called


def run(elf,entry,contract):
    if not isinstance(contract,dict) or not contract:
        raise ValueError('must provide independent callee ABI manifest')
    scan=analyze(elf)
    if scan['symbols_used'] or scan['source_read']:
        raise ValueError('symbol/source contamination')
    entries=sorted(int(item['address'],16) for item in scan['candidate_entries'])
    if entry not in entries:
        raise ValueError('not discovered in stripped ELF')
    ix=entries.index(entry)
    stop=entries[ix+1] if ix+1<len(entries) else int(scan['text_address'],16)+scan['text_size_bytes']
    if stop-entry>4096 or stop<=entry:
        raise ValueError('uncertain function bounds')
    rows=parse_instructions(elf,entry,stop)
    cpp,callees=lift(entry,rows,contract)
    return cpp,{'status':'CPP_EMITTED_UNVALIDATED',
        'input_sha256':scan['input_sha256'],'symbols_used':False,'source_read':False,
        'entry':hex(entry),'instructions_translated':len(rows),
        'callee_sites':sorted([{'address':hex(addr),'kind':kind} for addr,kind in callees],key=lambda x:x['address']),
        'ABI_assumption':'uint32_t f(uint32_t board[16],uint32_t* score)',
        'behavioral_equivalence_proven':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--entry',required=True,type=lambda x:int(x,0))
    p.add_argument('--abi-contract',type=Path,required=True)
    p.add_argument('--cpp',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    roles=json.loads(a.abi_contract.read_text()).get('callee_abi_roles',{})
    manifest={int(k,0):v for k,v in roles.items()}
    cpp,report=run(a.elf,a.entry,manifest)
    a.cpp.parent.mkdir(parents=True,exist_ok=True);a.report.parent.mkdir(parents=True,exist_ok=True)
    a.cpp.write_text(cpp);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
