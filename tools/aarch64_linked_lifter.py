#!/usr/bin/env python3
"""Conservatively lift a tiny ARM64 function calling already lifted leaves.

Input ELF is stripped. Direct BL addresses are bound only through an independently
emitted candidate coverage JSON with matching ELF SHA, never through the original
source or symbol names. Only a specific balanced frame prologue/epilogue shape
is supported; nonmatching stack effects abort, not approximated.
"""
import argparse
import json
from pathlib import Path
import re
from aarch64_stripped_discovery import analyze
from aarch64_leaf_lifter import parse_instructions, regvalue, regset, operand, TARGET

PROLOGUE_STP='x29, x30, [sp, #-0x20]!'
PROLOGUE_FP='x29, sp'
FRAME_SAVE='x19, x20, [sp, #0x10]'
FRAME_LOAD='x19, x20, [sp, #0x10]'
EPILOGUE_LDP='x29, x30, [sp], #0x20'
SUPPORTED={'stp','ldp','mov','and','bl','tbz','tbnz','ret','b','nop'}


def lift_linked(entry,rows,callee_map):
    pcs={pc for pc,_,_ in rows}
    if len(rows)<6 or len(rows)>512 or len(pcs)!=len(rows) or \
       any(pc!=entry+4*i for i,(pc,_,_) in enumerate(rows)):
        raise ValueError('incomplete/ambiguous linked function')
    if [(r[1],r[2]) for r in rows[:3]] != [
        ('stp',PROLOGUE_STP),('mov',PROLOGUE_FP),('stp',FRAME_SAVE)]:
        raise ValueError('unrecognized paired-register frame prologue')
    if [(r[1],r[2]) for r in rows if r[1]=='ldp'] != [
        ('ldp',FRAME_LOAD),('ldp',EPILOGUE_LDP)]:
        raise ValueError('incomplete or unbalanced paired-register frame restore')
    if sum(1 for row in rows if row[1]=='stp') != 2:
        raise ValueError('unexpected paired store in body')
    restore = next(i for i,row in enumerate(rows) if row[1]=='ldp')
    if [(r[1],r[2]) for r in rows[restore:restore+3]] != [
        ('ldp',FRAME_LOAD),('ldp',EPILOGUE_LDP),('ret','')]:
        raise ValueError('frame must restore immediately before return')
    stmts=[]; called=set()
    for pc,op,args in rows:
        if op not in SUPPORTED:
            raise ValueError(f'unsupported linked opcode {pc:#x}: {op} {args}')
        operands=[x.strip() for x in args.split(',')] if args else []
        code=None
        if op=='stp' and args in (PROLOGUE_STP,FRAME_SAVE):
            code='; /* matched balanced machine frame save, managed by C++ ABI */'
        elif op=='ldp' and args in (FRAME_LOAD,EPILOGUE_LDP):
            code='; /* matched balanced machine frame restore, managed by C++ ABI */'
        elif op=='mov' and args==PROLOGUE_FP:
            code='; /* validated frame-pointer initialization */'
        elif op=='mov' and len(operands)==2:
            code=regset(operands[0],operand(operands[1]))
        elif op=='and' and len(operands)==3:
            code=regset(operands[0],f'{regvalue(operands[1])} & {operand(operands[2])}')
        elif op in ('tbz','tbnz') and len(operands)==3:
            m=TARGET.fullmatch(operands[2]);to=int(m[1],16) if m else None
            bit=re.fullmatch(r'#(0x[0-9a-fA-F]+|\d+)',operands[1])
            if to not in pcs or not bit or not 0<=int(bit[1],0)<32:
                raise ValueError('invalid test-and-branch target or bit')
            comparison='==' if op=='tbz' else '!='
            code=f'if (({regvalue(operands[0])} & (1U << {int(bit[1],0)})) {comparison} 0) goto pc_{to:x};'
        elif op=='bl' and len(operands)==1:
            m=TARGET.fullmatch(operands[0]);to=int(m[1],16) if m else None
            kind=callee_map.get(to)
            if kind not in ('read_only_leaf','mutating_leaf'):
                raise ValueError('BL callee not in previously lifted ELF candidates')
            called.add((to,kind))
            if kind=='read_only_leaf':
                call=f'r[0] = uint32_t(recovered_{to:x}(reinterpret_cast<const uint32_t*>(uintptr_t(r[0]))));'
            else:
                call=f'recovered_{to:x}(reinterpret_cast<uint32_t*>(uintptr_t(r[0]))); r[0]=0;'
            code='{ '+call+' for(unsigned j=1;j<=18;j++) r[j]=0; }'
        elif op=='b' and len(operands)==1:
            m=TARGET.fullmatch(operands[0]);to=int(m[1],16) if m else None
            if to not in pcs: raise ValueError('out-of-range linked branch')
            code=f'goto pc_{to:x};'
        elif op=='ret' and not args:
            code='return uint32_t(r[0]);'
        elif op=='nop' and not args:
            code=';'
        if code is None: raise ValueError(f'unsupported operands {pc:#x}: {op} {args}')
        stmts.append(f' pc_{pc:x}: if (++budget>1000000ULL) throw std::runtime_error("linked instruction budget exceeded"); {code}')
    if not called: raise ValueError('no verified callee found')
    declarations=[]
    for target,kind in sorted(called):
        if kind=='read_only_leaf':declarations.append(f'extern "C" int32_t recovered_{target:x}(const uint32_t*);')
        else:declarations.append(f'extern "C" void recovered_{target:x}(uint32_t*);')
    output='\n'.join(['#include <cstdint>','#include <stdexcept>',*declarations,
        f'extern "C" uint32_t recovered_{entry:x}(uint32_t* input) {{',
        ' if (!input) throw std::invalid_argument("board pointer required");',
        ' uint64_t r[31] = {}; uint64_t budget=0; r[0]=uint64_t(uintptr_t(input));',
        *stmts, ' throw std::runtime_error("unreachable control flow fallthrough");','}',''])
    return output,sorted([{'address':hex(t),'type':k} for t,k in called],key=lambda x:x['address'])


def run(elf,entry,coverage):
    scan=analyze(elf)
    if scan['symbols_used'] or scan['source_read']:
        raise ValueError('symbols/source contamination')
    cov=json.loads(Path(coverage).read_text())
    if cov.get('stripped_elf_sha256')!=scan['input_sha256'] or cov.get('source_read') is not False or cov.get('symbols_used') is not False:
        raise ValueError('coverage metadata ELF hash/source mismatch')
    callee_map={int(row['address'],16):row['lifter'] for row in cov['functions'] if row['status']=='CPP_EMITTED_UNVALIDATED'}
    entries=sorted(int(row['address'],16) for row in scan['candidate_entries'])
    if entry not in entries: raise ValueError('not a stripped ELF candidate entry')
    idx=entries.index(entry)
    stop=entries[idx+1] if idx+1<len(entries) else int(scan['text_address'],16)+scan['text_size_bytes']
    if stop<=entry or stop-entry>16384:raise ValueError('function exceeds bounded size')
    rows=parse_instructions(elf,entry,stop)
    source,callees=lift_linked(entry,rows,callee_map)
    return source,{'status':'LINKED_CPP_LIFTED_NOT_VALIDATED','entry':hex(entry),
        'input_sha256':scan['input_sha256'],'source_read':False,'symbols_used':False,
        'instruction_count':len(rows),'callee_candidates':callees,
        'assumed_abi':'uint32_t(uint32_t*)','return_value_validated':False,
        'board_mutation_validated':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--coverage',type=Path,required=True)
    p.add_argument('--entry',type=lambda s:int(s,0),required=True)
    p.add_argument('--cpp',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    code,report=run(a.elf,a.entry,a.coverage)
    a.cpp.parent.mkdir(parents=True,exist_ok=True)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.cpp.write_text(code)
    a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
