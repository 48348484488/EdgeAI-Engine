#!/usr/bin/env python3
"""Fail-closed source-blind ARM64 scalar C++ lift: one unsigned 32-bit argument.

Supports only a small explicit subset of register ALU, comparisons, select
and branches. ABI uint32_t(uint32_t) is a TEST ASSUMPTION, not inferred type.
No symbols, originals or decompiler output are consumed by this program.
"""
import argparse
import json
from pathlib import Path
from aarch64_leaf_lifter import parse_instructions, regvalue, regset, operand, REG, TARGET
from aarch64_stripped_discovery import analyze

COND={'eq':'Z','ne':'!Z','hi':'C && !Z','ls':'!C || Z',
      'ge':'N==V','lt':'N!=V','gt':'!Z && N==V','le':'Z || N!=V',
      'hs':'C','lo':'!C'}
ALLOWED={'add','sub','and','mov','cmp','csel','cset','ret','nop','b','cbz','cbnz'} | {'b.'+s for s in COND}


def lift_scalar(entry, rows):
    pcs={pc for pc,_,_ in rows}
    if len(rows)<2 or len(rows)>4096 or len(pcs)!=len(rows) or \
       any(pc!=entry+4*i for i,(pc,_,_) in enumerate(rows)):
        raise ValueError('incomplete or ambiguous function range')
    has_ret=has_cond=False
    code=[]
    for pc,op,args in rows:
        if op not in ALLOWED:
            raise ValueError(f'unsupported scalar opcode {pc:#x}: {op} {args}')
        operands=[item.strip() for item in args.split(',')] if args else []
        stmt=None
        if op=='nop' and not args:
            stmt=';'
        elif op=='ret' and args in ('','x30'):
            stmt='return uint32_t(r[0]);';has_ret=True
        elif op=='mov' and len(operands)==2:
            stmt=regset(operands[0],operand(operands[1]))
        elif op in ('add','sub','and') and len(operands)==3:
            lhs=regvalue(operands[1]);rhs=operand(operands[2]); operation={'add':'+','sub':'-','and':'&'}[op]
            stmt=regset(operands[0],f'{lhs} {operation} {rhs}')
        elif op=='cmp' and len(operands)==2:
            lhs=regvalue(operands[0]);rhs=operand(operands[1]);m=REG.fullmatch(operands[0])
            if not m: raise ValueError('unknown comparison width')
            width=32 if m[1]=='w' else 64
            u=f'uint{width}_t'
            stmt=(f'{{ {u} a={u}({lhs}),b={u}({rhs}),d=a-b; '
                  f'Z=(d==0); N=((d>>{width-1})&1)!=0; C=(a>=b); '
                  f'V=(((a^b)&(a^d))>>{width-1})!=0; }}')
            has_cond=True
        elif op=='csel' and len(operands)==4:
            cond=COND.get(operands[3]);
            if cond is None: raise ValueError('unknown csel condition')
            stmt=regset(operands[0],f'(({cond}) ? {regvalue(operands[1])} : {regvalue(operands[2])})')
        elif op=='cset' and len(operands)==2:
            cond=COND.get(operands[1]);
            if cond is None: raise ValueError('unknown cset condition')
            stmt=regset(operands[0],f'(({cond}) ? 1 : 0)')
        elif (op=='b' or op.startswith('b.')) and len(operands)==1:
            target=TARGET.fullmatch(operands[0]);dst=int(target[1],16) if target else None
            if dst not in pcs: raise ValueError('branch outside function')
            cond='true' if op=='b' else COND[op[2:]]
            stmt=f'if ({cond}) goto pc_{dst:x};'
        elif op in ('cbz','cbnz') and len(operands)==2:
            target=TARGET.fullmatch(operands[1]);dst=int(target[1],16) if target else None
            if dst not in pcs: raise ValueError('branch outside function')
            stmt=f'if ({regvalue(operands[0])} {"==" if op=="cbz" else "!="} 0) goto pc_{dst:x};'
        if stmt is None: raise ValueError(f'unknown scalar operand {pc:#x}: {op} {args}')
        code.append(f' pc_{pc:x}: if (++budget>1000000ULL) throw std::runtime_error("instruction budget exceeded"); {stmt}')
    if not has_ret or not has_cond:
        raise ValueError('unsupported scalar function: no return or compare')
    return '\n'.join(['#include <cstdint>','#include <stdexcept>',
       f'extern "C" uint32_t recovered_{entry:x}(uint32_t arg) {{',
       ' uint64_t r[31]={}; bool N=false,Z=false,C=false,V=false; uint64_t budget=0;',
       ' r[0]=arg;', *code,
       ' throw std::runtime_error("fell through function");','}',''])


def run(elf,entry):
    evidence=analyze(elf)
    if evidence['symbols_used'] or evidence['source_read']:
        raise ValueError('blind analysis input invalid')
    entries=sorted(int(row['address'],16) for row in evidence['candidate_entries'])
    if entry not in entries: raise ValueError('not a discovered entry candidate')
    i=entries.index(entry)
    stop=entries[i+1] if i+1<len(entries) else int(evidence['text_address'],16)+evidence['text_size_bytes']
    if stop-entry>16384 or stop<=entry: raise ValueError('unsafe function interval')
    rows=parse_instructions(elf,entry,stop)
    cpp=lift_scalar(entry,rows)
    return cpp,{'status':'SCALAR_CPP_LIFTED_NOT_VALIDATED','entry':hex(entry),
      'next_candidate':hex(stop),'instruction_count':len(rows),
      'input_sha256':evidence['input_sha256'],'symbols_used':False,'source_read':False,
      'assumed_abi':'uint32_t(uint32_t)','behaviorally_validated':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--entry',type=lambda s:int(s,0),required=True)
    p.add_argument('--cpp',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    cpp,report=run(a.elf,a.entry)
    a.cpp.parent.mkdir(parents=True,exist_ok=True)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.cpp.write_text(cpp)
    a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
