#!/usr/bin/env python3
"""Conservative binary-only translator for straight-line ARM64 printf sequences.

The only input is a stripped AArch64 ELF. It reads .text, read-only .rodata,
PLT names (imported libc symbols remain in stripped binaries), and never reads
any original game C or .symtab. Callee-saved registers x19..x28 are preserved
across external BL according to the declared AAPCS64 calling convention.

A tiny supported printf grammar (%%, %d, %*s, %s) and safe constant strings
are translated into native C++ using std::printf. Unknown opcodes, memory
writes, variable-driven arguments, and unresolved control flow fail closed.
"""
import argparse
import json
import re
from pathlib import Path
from aarch64_printf_lifter import load_rodata, get_cstring, plt_symbols
from aarch64_leaf_lifter import parse_instructions
from aarch64_stripped_discovery import analyze

MOVE = re.compile(r'^([wx])(\d+), ([wx])(\d+)$')
MOVI = re.compile(r'^([wx])(\d+), #(-?0x[0-9a-fA-F]+|-?\d+)$')
ADRP = re.compile(r'^x(\d+), (0x[0-9a-fA-F]+)$')
ADDI = re.compile(r'^x(\d+), x(\d+), #(0x[0-9a-fA-F]+|\d+)$')
PAIR = re.compile(r'^(x(?:[12]?\d|30)), (x(?:[12]?\d|30)), \[sp, #(?P<off>0x[0-9a-fA-F]+|\d+)\]$')
ONE = re.compile(r'^(x(?:[12]?\d|30)), \[sp, #(0x[0-9a-fA-F]+|\d+)\]$')
OPEN = re.compile(r'^x29, x30, \[sp, #-(0x[0-9a-fA-F]+|\d+)\]!$')
CLOSE = re.compile(r'^x29, x30, \[sp\], #(0x[0-9a-fA-F]+|\d+)$')
BL = re.compile(r'^0x[0-9a-fA-F]+$')


def printf_items(data):
    """Return ordered variadic argument roles; reject unsafe format families."""
    try: fmt = data.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc: raise ValueError('invalid UTF-8 format string') from exc
    items=[];i=0
    while i<len(fmt):
        if fmt[i]!='%':i+=1;continue
        if i+1<len(fmt) and fmt[i+1]=='%':i+=2;continue
        if fmt.startswith('%*s',i):items.extend(('int','cstring'));i+=3;continue
        m=re.match(r'%[-+ 0#]*\d{0,3}(?:\.\d{1,3})?d',fmt[i:])
        if m:items.append('int');i+=len(m[0]);continue
        if fmt.startswith('%s',i):items.append('cstring');i+=2;continue
        raise ValueError('unsupported/unsafe printf format at %s' % repr(fmt[i:i+12]))
    if len(items)>4:raise ValueError('too many variadic arguments')
    return items


def _const_bytes(data):
    return '{ '+', '.join('0x%02x' % b for b in data+b'\x00')+' }'


def _get(regs, index, width='x'):
    if index not in regs:raise ValueError(f'unproved constant register {width}{index}')
    val=regs[index]
    return val & (0xffffffff if width=='w' else (1<<64)-1)


def _frame_evidence(rows):
    if len(rows)<8 or rows[0][1]!='stp' or rows[1][1:]!=('mov','x29, sp') or rows[-2][1]!='ldp' or rows[-1][1:]!=('ret',''):
        raise ValueError('not a straight-line balanced non-leaf function')
    opening=OPEN.fullmatch(rows[0][2]);closing=CLOSE.fullmatch(rows[-2][2])
    if not opening or not closing or int(opening[1],0)!=int(closing[1],0):
        raise ValueError('unbalanced stack frame')
    frame=int(opening[1],0)
    if frame<16 or frame>256 or frame%16:raise ValueError('unsupported frame depth')
    saves={};restores={}
    for pc,op,args in rows[2:-2]:
        if op in ('stp','ldp'):
            match=PAIR.fullmatch(args)
            if not match:raise ValueError('unknown pair access on stack')
            regs=(match[1],match[2]);off=int(match['off'],0)
            if not all(19<=int(x[1:])<=28 for x in regs) or off<16 or off+16>frame:
                raise ValueError('pair out of bounded callee-saved stack slots')
            key=(regs,off);chosen=saves if op=='stp' else restores
            chosen[key]=chosen.get(key,0)+1
        elif op in ('str','ldr'):
            match=ONE.fullmatch(args)
            if not match:raise ValueError('unknown scalar access on stack')
            reg=match[1];off=int(match[2],0)
            if not 19<=int(reg[1:])<=28 or off<16 or off+8>frame:
                raise ValueError('scalar outside frame or not preserved register')
            key=((reg,),off);chosen=saves if op=='str' else restores
            chosen[key]=chosen.get(key,0)+1
    if not saves or saves!=restores or any(x!=1 for x in saves.values()):
        raise ValueError('unbalanced or missing callee-saved stack effects')
    return {'frame_size':frame,'saved_register_groups':len(saves)}


def lift(elf, entry, stop):
    rows=parse_instructions(elf,entry,stop)
    if len(rows)>512:raise ValueError('oversized printer')
    frame=_frame_evidence(rows)
    symbols=plt_symbols(elf)
    rodata=load_rodata(elf)
    regs={};output=[];calls=[]
    for pc,op,args in rows[2:-2]:
        if op in ('stp','ldp','str','ldr'):
            # Checked frame-only register preservation by _frame_evidence.
            continue
        if op=='mov':
            m=MOVI.fullmatch(args)
            if m:
                kind,index,value=m.groups();index=int(index)
                if index>30:raise ValueError('bad dest register')
                val=int(value,0) & (0xffffffff if kind=='w' else (1<<64)-1)
                regs[index]=val
                continue
            m=MOVE.fullmatch(args)
            if not m:raise ValueError(f'unsupported mov: {args}')
            kind,i,src_kind,j=m.groups();i=int(i);j=int(j)
            if i>30 or j>30:raise ValueError('bad move register')
            if kind=='x' and src_kind=='w':raise ValueError('unsupported width extension')
            regs[i]=_get(regs,j,src_kind) & (0xffffffff if kind=='w' else (1<<64)-1)
            continue
        if op=='adrp':
            m=ADRP.fullmatch(args)
            if not m:raise ValueError('unknown ADRP provenance')
            i=int(m[1]);page=int(m[2],16)
            if i>30 or page%4096:raise ValueError('unaligned ADRP')
            regs[i]=page
            continue
        if op=='add':
            m=ADDI.fullmatch(args)
            if not m:raise ValueError('only immediate xADD allowed')
            i,j,delta=int(m[1]),int(m[2]),int(m[3],0)
            if i>30 or j>30 or delta>4095:raise ValueError('out of range ADD')
            regs[i]=(_get(regs,j)+delta)&((1<<64)-1)
            continue
        if op=='bl':
            if not BL.fullmatch(args) or symbols.get(int(args,16))!='__printf_chk':
                raise ValueError(f'unmodeled external/internal BL at {hex(pc)}: {args}')
            if _get(regs,0,'w')!=2:raise ValueError('unverified __printf_chk flag')
            fmt=get_cstring(_get(regs,1),rodata)
            layout=printf_items(fmt)
            params=[]
            for argno,role in enumerate(layout,start=2):
                val=_get(regs,argno)
                if role=='int':
                    num=val & 0xffffffff
                    params.append(('int',num if num < (1<<31) else num-(1<<32)))
                elif role=='cstring':
                    data=get_cstring(val,rodata)
                    if len(data)>1024:raise ValueError('literal too long')
                    params.append(('cstring',data))
            call_index=len(calls)
            source_name=f'fmt_{call_index}'
            output.append('  static const unsigned char '+source_name+'[] = '+_const_bytes(fmt)+';')
            rendered=[]
            for i,(role,value) in enumerate(params):
                if role=='int':rendered.append(str(value))
                else:
                    name=f'arg_{call_index}_{i}'
                    output.append('  static const unsigned char '+name+'[] = '+_const_bytes(value)+';')
                    rendered.append('reinterpret_cast<const char*>('+name+')')
            tail=', '+', '.join(rendered) if rendered else ''
            output.append('  std::printf(reinterpret_cast<const char*>('+source_name+')'+tail+');')
            calls.append({'at':hex(pc),'format_hex':fmt.hex(),'arguments':[
                {'kind':role, 'value':value if role=='int' else value.hex()} for role,value in params]})
            # AAPCS64 x0-x18 are caller-saved; x19-x28 must survive.
            regs={k:v for k,v in regs.items() if 19<=k<=28}
            continue
        raise ValueError(f'unsupported printer instruction at {hex(pc)}: {op} {args}')
    if not calls:raise ValueError('no modeled prints')
    cpp='\n'.join(['#include <cstdint>','#include <cstdio>',
                   f'extern "C" void recovered_{entry:x}() {{',*output,'}',''])
    manifest={'entry':hex(entry),'status':'CPP_EMITTED_UNVALIDATED',
         'instructions_translated':len(rows),'source_read':False,'symbols_used':False,
         'data_from_elf_rodata':True,'dynamic_imports_recognized':True,
         'printf_calls':len(calls),'calls':calls,
         'abi_assumption':'void()','behavioral_equivalence_proven':False,
         **frame}
    return cpp,manifest


def run(elf,entry):
    scan=analyze(elf)
    if scan['symbols_used'] or scan['source_read']:
        raise ValueError('unexpected source or symbols in input')
    entries=sorted(int(x['address'],16) for x in scan['candidate_entries'])
    if entry not in entries:raise ValueError('entry not independently discovered')
    ix=entries.index(entry)
    end=entries[ix+1] if ix+1<len(entries) else int(scan['text_address'],16)+scan['text_size_bytes']
    code,evidence=lift(elf,entry,end)
    evidence['input_sha256']=scan['input_sha256']
    return code,evidence


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--entry',type=lambda s:int(s,0),required=True)
    p.add_argument('--cpp',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    code,record=run(a.elf,a.entry)
    a.cpp.parent.mkdir(parents=True,exist_ok=True)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.cpp.write_text(code,encoding='utf-8')
    a.report.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k!='calls'},indent=2))

if __name__=='__main__':main()
