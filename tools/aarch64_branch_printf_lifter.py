#!/usr/bin/env python3
"""Source-blind bounded AArch64 branch/printf/linked-scalar to C++ lifter.

This intentionally accepts only a known, declared ABI (u32,u8,u8)->void,
proven matched callee-saved stack frame, source-independent scalar callee,
and a limited register/cmp/branch/printf instruction subset. Literal strings
and dynamic PLT imports are recovered exclusively from the stripped ELF.
No game function names or hard-coded original code addresses are used.
"""
import argparse
import json
from pathlib import Path
import re
from aarch64_printf_lifter import load_rodata, plt_symbols
from aarch64_leaf_lifter import parse_instructions
from aarch64_static_printf_sequence_lifter import printf_items
from aarch64_stripped_discovery import analyze

REG=re.compile(r'^([wx])([0-9]|[12][0-9]|30)$')
IMM=re.compile(r'^#(-?0x[0-9a-fA-F]+|-?[0-9]+)$')
TARG=re.compile(r'^0x([0-9a-fA-F]+)$')
OPEN=re.compile(r'^x29, x30, \[sp, #-(0x[0-9a-fA-F]+|[0-9]+)\]!$')
CLOSE=re.compile(r'^x29, x30, \[sp\], #(0x[0-9a-fA-F]+|[0-9]+)$')
PAIR=re.compile(r'^(x(?:[12]?\d|30)), (x(?:[12]?\d|30)), \[sp, #(0x[0-9a-fA-F]+|[0-9]+)\]$')


def _parts(s):
    # lsl #N stays a fourth comma-separated AArch64 operand.
    return [x.strip() for x in s.split(',')] if s else []


def _reg(token):
    m=REG.fullmatch(token)
    if not m:raise ValueError('unknown register '+token)
    return int(m[2]),m[1]


def _read(token):
    m=IMM.fullmatch(token)
    if m:return str(int(m[1],0))+'ULL'
    i,w=_reg(token)
    return f'uint32_t(r[{i}])' if w=='w' else f'r[{i}]'


def _write(token,expr):
    i,w=_reg(token)
    return f'r[{i}]=uint{32 if w=="w" else 64}_t({expr});'


def _literal(b):
    return ', '.join(f'0x{v:02x}' for v in b)


def _bounded_frame(rows):
    if len(rows)<10 or rows[0][1]!='stp' or rows[1][1:]!=('mov','x29, sp'):
        raise ValueError('not a frame-bearing nonleaf function')
    m=OPEN.fullmatch(rows[0][2])
    end_points=[(pc,int(n[1],0)) for pc,op,args in rows if op=='ldp' and (n:=CLOSE.fullmatch(args))]
    if not m or len(end_points)!=1 or int(m[1],0)!=end_points[0][1]:
        raise ValueError('unbalanced frame header/footer')
    epilogue=end_points[0][0]
    if (epilogue+4,'ret','') not in rows:raise ValueError('unpaired return after frame restore')
    size=int(m[1],0)
    if size<16 or size>256 or size%16:raise ValueError('unsupported stack frame depth')
    saved={};restored={}
    for pc,op,arg in rows[2:]:
        if op not in ('stp','ldp') or pc==epilogue:continue
        q=PAIR.fullmatch(arg)
        if not q:raise ValueError('unrecognized stack pair '+arg)
        a,b,off=q[1],q[2],int(q[3],0)
        if (not all(19<=int(x[1:])<=28 for x in (a,b)) or off<16 or off+16>size or off%8):
            raise ValueError('stack pair outside declared callee-saved region')
        dst=saved if op=='stp' else restored
        key=(a,b,off)
        dst[key]=dst.get(key,0)+1
    if not saved or saved!=restored or any(v!=1 for v in saved.values()):
        raise ValueError('callee-saved frame not uniquely balanced')
    return size,len(saved),epilogue


def _string_roles(rodata):
    base,data=rodata
    result=[]
    for off,byte in enumerate(data):
        if not byte or (off and data[off-1]!=0):continue
        end=data.find(b'\0',off)
        if end<0 or end-off>1024:continue
        b=data[off:end]
        try:roles=printf_items(b.replace(b"%*d",b"%d%d"))
        except (ValueError,UnicodeDecodeError):continue
        if len(roles)>4:continue
        result.append((base+off, b,roles))
    return result


def _printf_runtime(rodata):
    base,data=rodata
    strings=_string_roles(rodata)
    out=[f' static const unsigned char rodata[]={{{_literal(data)}}};',
         f' constexpr uint64_t ro_start={base}ULL;',
         f' constexpr uint64_t ro_end={base+len(data)}ULL;',
         ' auto bounded_cstr=[&](uint64_t addr)->const char* {',
         '   if(addr<ro_start||addr>=ro_end)throw std::runtime_error("cstring outside ELF .rodata");',
         '   const unsigned char *p=rodata+(addr-ro_start);',
         '   if(!std::memchr(p,0,ro_end-addr))throw std::runtime_error("unterminated ELF cstring");',
         '   return reinterpret_cast<const char*>(p);',
         ' };',
         ' auto checked_printf=[&]()->int {',
         '   if(uint32_t(r[0])!=2)throw std::runtime_error("unsupported __printf_chk flag");',
         '   const char *fmt=bounded_cstr(r[1]);',
         '   switch(r[1]) {']
    for addr,b,roles in strings:
        if roles==[]:params=[]
        elif roles==['int']:params=['int32_t(uint32_t(r[2]))']
        elif roles==['int','int']:params=['int32_t(uint32_t(r[2]))','int32_t(uint32_t(r[3]))']
        elif roles==['int','int','int','cstring']:
            params=['int32_t(uint32_t(r[2]))','int32_t(uint32_t(r[3]))','int32_t(uint32_t(r[4]))','bounded_cstr(r[5])']
        elif roles==['int','cstring']:
            params=['int32_t(uint32_t(r[2]))','bounded_cstr(r[3])']
        else:continue
        out.append(f'    case {addr}ULL: return std::printf(fmt{", "+", ".join(params) if params else ""});')
    out+=['    default: throw std::runtime_error("unrecognized ELF format string at printf call");',
          '   }',' };']
    return out, len(strings)


def lift(elf,entry,stop,scalar_callees):
    rows=parse_instructions(elf,entry,stop)
    size,save_groups,epilogue=_bounded_frame(rows)
    if len(rows)>512:raise ValueError('complex printer exceeds limit')
    plt=plt_symbols(elf)
    rodata=load_rodata(elf)
    valid_pcs={pc for pc,_,_ in rows}
    if not scalar_callees:raise ValueError('no proven scalar leaf contract')
    source=[ '#include <cstdint>','#include <cstdio>','#include <cstring>','#include <stdexcept>']
    for t in sorted(scalar_callees):source.append(f'extern "C" uint32_t recovered_{t:x}(uint32_t);')
    source.extend([f'extern "C" void recovered_{entry:x}(uint32_t arg0,uint8_t arg1,uint8_t arg2) {{',
       ' uint64_t r[31]={}; bool N=false,Z=false,C=false,V=false;',
       ' uint64_t budget=0;',
       ' r[0]=arg0; r[1]=arg1; r[2]=arg2;'])
    printf_runtime,string_count=_printf_runtime(rodata)
    source+=printf_runtime
    num_printf=0; num_callee=0
    supported={'stp','ldp','mov','and','cbz','cbnz','adrp','add','bl','mul','cmp','b','b.ls','b.hi','csel','ret'}
    frame_idxs=[]
    for pc,op,args in rows:
        if op not in supported:raise ValueError(f'unsupported opcode at {hex(pc)}: {op} {args}')
        p=_parts(args)
        expr=None
        if pc==rows[0][0]:
            if op!='stp' or not OPEN.fullmatch(args):raise ValueError('missing validated prologue')
            expr=';'
        elif pc==rows[1][0]:
            if (op,args)!=('mov','x29, sp'):raise ValueError('missing frame-pointer setup')
            expr=';'
        elif pc==epilogue:
            if op!='ldp' or not CLOSE.fullmatch(args):raise ValueError('missing validated epilogue')
            expr=';'
        elif op in ('stp','ldp'):
            if not PAIR.fullmatch(args):raise ValueError('unverified pair access')
            frame_idxs.append(pc)
            expr=';'
        elif op=='ret' and args in ('','x30'):
            expr='return;'
        elif op=='mov' and len(p)==2:
            expr=_write(p[0],_read(p[1]))
        elif op=='and' and len(p)==3 and IMM.fullmatch(p[2]):
            expr=_write(p[0],f'({_read(p[1])} & {_read(p[2])})')
        elif op=='adrp' and len(p)==2 and TARG.fullmatch(p[1]):
            if p[0][0]!='x':raise ValueError('invalid ADRP dest width')
            val=int(p[1],16)
            if val%4096:raise ValueError('unaligned ADRP page')
            expr=_write(p[0],str(val)+'ULL')
        elif op=='add' and len(p) in (3,4):
            rhs=_read(p[2]);lhs=_read(p[1]);
            if len(p)==4:
                m=re.fullmatch(r'lsl #(\d+)',p[3])
                if not m or int(m[1])>4:raise ValueError('unsupported operand shift')
                rhs=f'({rhs} << {int(m[1])})'
            expr=_write(p[0],f'({lhs}+{rhs})')
        elif op=='mul' and len(p)==3:
            expr=_write(p[0],f'({_read(p[1])}*{_read(p[2])})')
        elif op=='cmp' and len(p)==2:
            _,width=_reg(p[0]);u='uint32_t' if width=='w' else 'uint64_t';sh=31 if width=='w' else 63
            expr=(f'{{ {u} a={u}({_read(p[0])}),b={u}({_read(p[1])}),d={u}(a-b);'
                  f' Z=(d==0); N=bool((d>>{sh})&1); C=(a>=b); V=bool(((a^b)&(a^d))>>{sh}); }}')
        elif op in ('cbz','cbnz') and len(p)==2:
            m=TARG.fullmatch(p[1]);target=int(p[1],0) if m else -1
            if target not in valid_pcs:raise ValueError('branch outside candidate function')
            expr=f'if ({_read(p[0])}{"==" if op=="cbz" else "!="}0) goto pc_{target:x};'
        elif op in ('b','b.ls','b.hi') and len(p)==1:
            target=int(p[0],0) if TARG.fullmatch(p[0]) else -1
            if target not in valid_pcs:raise ValueError('branch outside candidate function')
            cond={'b':'true','b.ls':'!C || Z','b.hi':'C && !Z'}[op]
            expr=f'if ({cond}) goto pc_{target:x};'
        elif op=='csel' and len(p)==4:
            c={'hi':'C && !Z','ls':'!C || Z','eq':'Z','ne':'!Z'}.get(p[3])
            if c is None:raise ValueError('unsupported CSEL condition')
            expr=_write(p[0],f'(({c})?{_read(p[1])}:{_read(p[2])})')
        elif op=='bl' and len(p)==1 and TARG.fullmatch(p[0]):
            target=int(p[0],0)
            if plt.get(target)=='__printf_chk':
                expr='{ uint32_t x0=uint32_t(checked_printf()); r[0]=x0; }';num_printf+=1
            elif target in scalar_callees:
                expr=f'{{ uint32_t x0=recovered_{target:x}(uint32_t(r[0])); r[0]=x0; }}';num_callee+=1
            else:raise ValueError(f'unsupported BL target {hex(target)} at {hex(pc)}')
        if expr is None:raise ValueError(f'unknown AArch64 instruction at {hex(pc)}: {op} {args}')
        source.append(f' pc_{pc:x}: if(++budget>10000)throw std::runtime_error("AArch64 translation budget"); {expr}')
    if not num_printf or not num_callee:raise ValueError('not a linked printer containing imported calls')
    source.append(' throw std::runtime_error("fell out of translated function");')
    source.append('}')
    return '\n'.join(source)+'\n',{
        'address':hex(entry),'instructions_translated':len(rows),
        'printf_call_sites':num_printf,'internal_scalar_call_sites':num_callee,
        'data_read_from_elf':True,'dynamic_plt_symbols_read':True,'elf_symbols_used':False,
        'source_read':False,'symbols_used':False,'frame_bytes':size,'preserved_reg_pairs':save_groups,
        'rodata_formats_checked':string_count,'ABI_assumption':'void(uint32_t,uint8_t,uint8_t)',
        'behaviorally_validated':False,'original_game_function_name_used':False
    }


def discover(elf,coverage):
    scan=analyze(elf)
    if scan['source_read'] is not False or scan['symbols_used'] is not False:
        raise ValueError('discovery required stripped ELF provenance')
    candidates=sorted(int(x['address'],16) for x in scan['candidate_entries'])
    report=json.loads(Path(coverage).read_text())
    if report['binary_sha256']!=scan['input_sha256']:
        raise ValueError('coverage file sha does not match stripped ELF')
    scalar={int(x['address'],16) for x in report['functions'] if x.get('lifter')=='scalar_leaf' and x.get('status','').startswith('CPP_EMITTED')}
    matched=[];errors={}
    for i,entry in enumerate(candidates):
        stop=candidates[i+1] if i+1<len(candidates) else int(scan['text_address'],16)+scan['text_size_bytes']
        try:
            code,ev=lift(elf,entry,stop,scalar)
            matched.append((entry,code,ev))
        except (ValueError,KeyError,RuntimeError) as exc:
            errors[hex(entry)]=str(exc)
    if not matched:raise ValueError('no printer in stripped ELF accepted by bounded lifter')
    return matched,errors


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--coverage',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    matches,errors=discover(args.elf,args.coverage)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    report=[]
    for addr,code,ev in matches:
        (args.output_dir/f'candidate_{addr:x}.cpp').write_text(code)
        report.append(ev)
    (args.output_dir/'printer_coverage.json').write_text(json.dumps({'matches':report,'rejected':errors},indent=2)+'\n')
    print(json.dumps({'matches':report,'rejected_count':len(errors)},indent=2))


if __name__=='__main__':main()