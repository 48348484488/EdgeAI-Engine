#!/usr/bin/env python3
"""Source-blind AArch64 read-only 4x4 memory-loop with direct printer callback.

Supported ABI: void(uint32_t* board); strict 64-byte board memory aperture,
source-independent printer ABI from accepted leaf. No source/symbols consulted.
Unknown opcodes, stores and unrecognized call edges fail closed.
"""
import argparse,json,re
from pathlib import Path
from aarch64_printf_lifter import load_rodata,plt_symbols
from aarch64_leaf_lifter import parse_instructions
from aarch64_stripped_discovery import analyze
from aarch64_branch_printf_lifter import (_bounded_frame,_printf_runtime,_parts,_read,_write,
                                              _reg,IMM,TARG)
MEM_REG=re.compile(r'^(w(?:[0-9]|[12][0-9]|30)), \[(x(?:[0-9]|[12][0-9]|30)), (x(?:[0-9]|[12][0-9]|30)), lsl #(\d+)\]$')


def lift(elf,entry,stop,printer_callees):
    rows=parse_instructions(elf,entry,stop)
    frame_size,saved,epilogue=_bounded_frame(rows)
    if len(rows)>256 or not printer_callees:
        raise ValueError('missing printer callee or oversized function')
    valid_pcs={pc for pc,_,_ in rows};plt=plt_symbols(elf)
    code=['#include <cstdint>','#include <cstdio>','#include <cstring>','#include <stdexcept>']
    for t in sorted(printer_callees):
        code.append(f'extern "C" void recovered_{t:x}(uint32_t,uint8_t,uint8_t);')
    code.extend([f'extern "C" void recovered_{entry:x}(const uint32_t* board) {{',
         ' if(!board) throw std::invalid_argument("null board pointer");',
         ' constexpr uint64_t BBASE=0x10000000ULL;',
         ' uint64_t r[31]={}; bool N=false,Z=false,C=false,V=false;',
         ' uint64_t budget=0; r[0]=BBASE;',
         ' auto bounded_word=[&](uint64_t addr)->uint32_t {',
         '   if(addr<BBASE||addr>BBASE+60||((addr-BBASE)&3))',
         '     throw std::runtime_error("out of 64-byte board bounds");',
         '   uint32_t word=0;std::memcpy(&word,board+(addr-BBASE)/4,4); return word;',
         ' };'])
    fmt,string_count=_printf_runtime(load_rodata(elf))
    code+=fmt
    printer_calls=0;printf_calls=0;reads=0
    for pc,op,args in rows:
        p=_parts(args);expr=None
        if pc==rows[0][0]:
            if op!='stp':raise ValueError('frame prologue missing')
            expr=';'
        elif pc==rows[1][0]:
            if (op,args)!=('mov','x29, sp'):raise ValueError('frame-pointer setup missing')
            expr=';'
        elif pc==epilogue:
            if op!='ldp':raise ValueError('frame footer missing')
            expr=';'
        elif op in ('stp','ldp'):
            # All frame saves/restores already strictly checked.
            expr=';'
        elif op=='ret' and args in ('','x30'):
            expr='return;'
        elif op=='mov' and len(p)==2:
            expr=_write(p[0],_read(p[1]))
        elif op=='add' and len(p)==3:
            expr=_write(p[0],f'({_read(p[1])}+{_read(p[2])})')
        elif op=='and' and len(p)==3 and IMM.fullmatch(p[2]):
            expr=_write(p[0],f'({_read(p[1])}&{_read(p[2])})')
        elif op=='adrp' and len(p)==2 and TARG.fullmatch(p[1]):
            if p[0][0]!='x' or int(p[1],0)%4096:raise ValueError('invalid ADRP page')
            expr=_write(p[0],str(int(p[1],0))+'ULL')
        elif op=='ldr' and (m:=MEM_REG.fullmatch(args)):
            dst,base,offset,sh=m.groups()
            if int(sh)!=2:raise ValueError('unsupported indexed load scale')
            expr=_write(dst,f'bounded_word({_read(base)}+({_read(offset)}<<2))')
            reads+=1
        elif op=='cmp' and len(p)==2:
            _,width=_reg(p[0]);u='uint32_t' if width=='w' else 'uint64_t';sh=31 if width=='w' else 63
            expr=(f'{{ {u} a={u}({_read(p[0])}),b={u}({_read(p[1])}),d={u}(a-b);'
                  f' Z=(d==0); N=bool((d>>{sh})&1); C=(a>=b); V=bool(((a^b)&(a^d))>>{sh}); }}')
        elif op in ('b','b.ne','b.eq','b.hi','b.ls') and len(p)==1:
            target=int(p[0],0) if TARG.fullmatch(p[0]) else -1
            if target not in valid_pcs:raise ValueError('branch target outside bounded function')
            cond={'b':'true','b.ne':'!Z','b.eq':'Z','b.hi':'C && !Z','b.ls':'!C || Z'}[op]
            expr=f'if({cond}) goto pc_{target:x};'
        elif op=='bl' and len(p)==1 and TARG.fullmatch(p[0]):
            target=int(p[0],0)
            if target in printer_callees:
                expr=f'recovered_{target:x}(uint32_t(r[0]),uint8_t(r[1]),uint8_t(r[2]));'
                printer_calls+=1
            elif plt.get(target)=='__printf_chk':
                expr='r[0]=uint32_t(checked_printf());';printf_calls+=1
            else:raise ValueError('unrecognized internal/external call target')
        if expr is None:raise ValueError(f'unsupported opcode at {hex(pc)}: {op} {args}')
        code.append(f' pc_{pc:x}: if(++budget>10000)throw std::runtime_error("instruction budget"); {expr}')
    if printer_calls!=1 or not printf_calls or not reads:
        raise ValueError('not a bounded memory printing caller')
    code+=[' throw std::runtime_error("control-flow fell outside translated function");','}']
    return '\n'.join(code)+'\n',{
        'address':hex(entry),'instructions_translated':len(rows),
        'internal_print_callees':printer_calls,'printf_call_sites':printf_calls,
        'indexed_memory_read_sites':reads,'board_region_bytes':64,
        'source_read':False,'symbols_used':False,
        'ABI_assumption':'void(const uint32_t* board)',
        'behaviorally_validated':False,'format_strings_from_elf':string_count,
        'frame_bytes':frame_size,'callee_saved_groups':saved}


def discover(elf,coverage,printer_reports):
    scan=analyze(elf)
    if scan['source_read'] is not False or scan['symbols_used'] is not False:
        raise ValueError('source-blind discovery required')
    original=json.loads(Path(coverage).read_text())
    if original['binary_sha256']!=scan['input_sha256']:
        raise ValueError('stale original ABI coverage')
    printer=json.loads(Path(printer_reports).read_text())
    available={int(x['address'],16) for x in printer['matches'] if x['ABI_assumption']=='void(uint32_t,uint8_t,uint8_t)'}
    if not available:raise ValueError('no accepted linked printer contract')
    entries=sorted(int(x['address'],16) for x in scan['candidate_entries'])
    found=[];rejected={}
    for i,entry in enumerate(entries):
        stop=entries[i+1] if i+1<len(entries) else int(scan['text_address'],16)+scan['text_size_bytes']
        try:
            result=lift(elf,entry,stop,available)
            found.append((entry,*result))
        except (ValueError,IndexError,KeyError) as ex:
            rejected[hex(entry)]=str(ex)
    if not found:raise ValueError('no caller accepted')
    return found,rejected


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf',type=Path)
    ap.add_argument('--coverage',type=Path,required=True)
    ap.add_argument('--printer-report',type=Path,required=True)
    ap.add_argument('--output-dir',type=Path,required=True)
    a=ap.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    found,rejected=discover(a.elf,a.coverage,a.printer_report)
    for entry,code,ev in found:
        (a.output_dir/f'candidate_{entry:x}.cpp').write_text(code)
    (a.output_dir/'caller_coverage.json').write_text(json.dumps({'matches':[x[2] for x in found],'rejected':rejected},indent=2)+'\n')
    print(json.dumps({'matches':[x[2] for x in found],'rejected_count':len(rejected)},indent=2))

if __name__=='__main__':main()