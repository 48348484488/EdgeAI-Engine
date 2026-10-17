#!/usr/bin/env python3
"""Source-blind ARM64-to-C++ register/stack lowering for bounded rand-dependent leaves.

The generator inspects ELF stripped executable bytes, LLVM ARM64 disassembly,
and dynamic PLT/GOT symbols. It never reads original game source, original
function names, or the .symtab oracle. Unknown operations fail closed.

Generated C++ models board memory (16 u32 words), bounded virtual stack,
PLT rand and stack-check guard, and direct interprocedural BL/RET control flow.
ABI assumption: void(uint32_t board[16]); executable-equivalence is not claimed.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from aarch64_stripped_discovery import analyze
from aarch64_leaf_lifter import parse_instructions
from aarch64_printf_lifter import plt_symbols

R = re.compile(r'^(w|x)([0-9]|[12][0-9]|30)$')
NUM = re.compile(r'^#?(-?0x[0-9a-fA-F]+|-?[0-9]+)$')
MEM = re.compile(r'^\[(sp|x(?:[12]?\d|30))(?:(?:, #(-?0x[0-9a-fA-F]+|-?\d+))|(?:, (x(?:[12]?\d|30)|w(?:[12]?\d|30))(?:, (lsl|uxtw) #(\d+))?))?\](!?)$')
POST = re.compile(r'^\[(sp|x(?:[12]?\d|30))\], #(-?0x[0-9a-fA-F]+|-?\d+)$')
ALLOWED = set('sub subs add adrp stp ldp str ldr mov cmp cmn cbnz cbz b b.ne b.eq bl ret ubfiz lsl udiv msub movk smull asr csel'.split())


def split_ops(arg):
    out=[]; curr=[]; depth=0
    for ch in arg:
        if ch=='[': depth+=1
        if ch==']': depth-=1
        if ch==',' and depth==0:
            out.append(''.join(curr).strip());curr=[]
        else:curr.append(ch)
    if curr:out.append(''.join(curr).strip())
    return out


def n(arg):
    m=NUM.fullmatch(arg)
    if not m:raise ValueError('not an integer '+arg)
    return int(m[1],0)


def rx(reg):
    if reg=='sp':return 'sp'
    if reg=='wzr' or reg=='xzr':return '0ULL'
    m=R.fullmatch(reg)
    if not m:raise ValueError('unsupported register '+reg)
    i=int(m[2]); return f'static_cast<uint64_t>(static_cast<uint32_t>(r[{i}]))' if m[1]=='w' else f'r[{i}]'


def assign(reg, expr):
    if reg in ('wzr','xzr'):return '; /* zero register discard */'
    if reg=='sp':return f'sp=uint64_t({expr});'
    m=R.fullmatch(reg)
    if not m:raise ValueError('unsupported write register '+reg)
    return f'r[{int(m[2])}]=static_cast<uint64_t>(static_cast<{"uint32_t" if m[1]=="w" else "uint64_t"}>({expr}));'


def val(x):
    return str(n(x))+'ULL' if x.startswith('#') else rx(x)


def address(op):
    """Translate one supported AArch64 addressing form, returning pre, expression, post."""
    m=MEM.fullmatch(op)
    if m:
        base,off,idx,kind,shift,wb=m.groups()
        if idx and off:raise ValueError('multiple memory offsets')
        if idx:
            if wb:raise ValueError('writeback indexed addressing not supported')
            sh=int(shift or 0)
            if sh>4 or kind not in (None,'lsl','uxtw'):raise ValueError('bad index modifier')
            if kind=='uxtw' and not idx.startswith('w'):
                raise ValueError('uxtw must extend w register')
            ext=f'(uint64_t(uint32_t({rx(idx)})))' if kind=='uxtw' else rx(idx)
            expr=f'({rx(base)} + ({ext} << {sh}))'
        else:
            expr=f'({rx(base)} + ({int(off,0) if off else 0}ULL))'
        return (f'{assign(base,expr)} ' if wb else ''),('sp' if wb else expr),''
    m=POST.fullmatch(op)
    if m:
        base,delta=m.groups()
        return '',rx(base),assign(base,f'{rx(base)} + {n(delta)}ULL')
    raise ValueError('unsupported memory operand '+op)


def flags_expr(left,right,bits,subtract=True):
    u=f'uint{bits}_t'
    op='-' if subtract else '+'
    overflow=f'(((a^b)&(a^d)) >> {bits-1})' if subtract else f'(((~(a^b))&(a^d)) >> {bits-1})'
    carry='a>=b' if subtract else 'd<a'
    return f'{{ {u} a={u}({left}), b={u}({right}), d=a{op}b; Z=d==0; N=((d >> {bits-1})&1)!=0; C={carry}; V=({overflow}&1)!=0; }}'


def second_arg(parts,width):
    if len(parts)==3:return val(parts[2])
    if len(parts)!=4:raise ValueError('not binary op')
    token=parts[3]
    m=re.fullmatch(r'(lsl|asr|uxtw) #(\d+)',token)
    if not m:raise ValueError('unsupported ALU modifier '+token)
    mod,shift=m[1],int(m[2])
    if shift>=width and mod!='uxtw':raise ValueError('shift outside width')
    if mod=='lsl':return f'({rx(parts[2])} << {shift})'
    if mod=='asr':return f'(static_cast<uint64_t>(static_cast<int{width}_t>({rx(parts[2])}) >> {shift}))'
    if not parts[2].startswith('w') or shift>4:raise ValueError('bad uxtw')
    return f'(uint64_t(uint32_t({rx(parts[2])})) << {shift})'


def lower(pc,op,args,sites,plt,guard_got):
    parts=split_ops(args)
    nextpc=f'0x{pc+4:x}ULL'
    stmt=None
    if op in ('add','sub','subs'):
        if len(parts)<3:raise ValueError('incomplete arithmetic')
        dest,left=parts[:2]
        if op=='subs' and dest.startswith('x'):
            bits=64
        else:
            bits=32 if dest.startswith('w') else 64
        v2=second_arg(parts,bits)
        opchar='-' if op.startswith('sub') else '+'
        stmt=assign(dest,f'{rx(left)} {opchar} {v2}')
        if op=='subs': stmt=flags_expr(rx(left),v2,bits,True)+stmt
    elif op=='mov':
        if len(parts)!=2:raise ValueError('mov operands')
        stmt=assign(parts[0],val(parts[1]))
    elif op=='movk':
        if len(parts) not in (2,3):raise ValueError('movk operands')
        shift=0
        if len(parts)==3:
            m=re.fullmatch(r'lsl #(\d+)',parts[2]);
            if not m:raise ValueError('movk shift')
            shift=int(m[1])
        bits=32 if parts[0].startswith('w') else 64
        if shift%16 or shift>=bits or not 0<=n(parts[1])<=0xffff:raise ValueError('bad MOVK')
        mask=(0xffff << shift)
        stmt=assign(parts[0],f'(({rx(parts[0])} & ~{mask}ULL) | ({n(parts[1])}ULL << {shift}))')
    elif op=='adrp':
        if len(parts)!=2 or not parts[0].startswith('x'):raise ValueError('bad adrp')
        a=n(parts[1]);
        if a%4096:raise ValueError('non-page-aligned ADRP')
        stmt=assign(parts[0],f'0x{a:x}ULL')
    elif op in ('str','ldr'):
        if len(parts)!=2:raise ValueError('unsupported load-store parameters '+args)
        r,mem=parts
        sz=8 if r.startswith('x') else 4 if r.startswith('w') else 0
        if sz==0:raise ValueError('invalid load width')
        pre,addr,post=address(mem)
        action=assign(r,f'read({addr}, {sz})') if op=='ldr' else f'write({addr}, {sz}, {rx(r)});'
        stmt=pre+action+post
    elif op in ('stp','ldp'):
        if len(parts)==4 and parts[2].endswith(']'):parts=[parts[0],parts[1],parts[2]+', '+parts[3]]
        if len(parts)!=3:raise ValueError('pair operands '+args)
        if not all(p.startswith('x') for p in parts[:2]):raise ValueError('only 64-bit register pair allowed')
        pre,addr,post=address(parts[2]); tmp=f'uint64_t taddr={addr};'
        if op=='stp': stmt=pre+tmp+f'write(taddr,8,{rx(parts[0])});write(taddr+8,8,{rx(parts[1])});'+post
        else:stmt=pre+tmp+assign(parts[0],'read(taddr,8)')+assign(parts[1],'read(taddr+8,8)')+post
    elif op in ('cmp','cmn'):
        if not len(parts) in (2,3):raise ValueError('unknown cmp operands')
        bits=32 if parts[0].startswith('w') else 64
        v2=second_arg(['_',parts[0],*parts[1:]],bits)
        stmt=flags_expr(rx(parts[0]),v2,bits,op=='cmp')
    elif op in ('cbnz','cbz'):
        if len(parts)!=2:raise ValueError('cbz operands')
        target=n(parts[1])
        if target not in sites:raise ValueError('branch outside lowered interval')
        expr='!=' if op=='cbnz' else '=='
        stmt=f'if ({rx(parts[0])} {expr} 0) {{pc=0x{target:x}ULL;break;}}'
    elif op=='b' or op.startswith('b.'):
        if len(parts)!=1:raise ValueError('branch operand')
        dest=n(parts[0])
        if dest not in sites:raise ValueError('branch outside lowered interval')
        cond={'b':'true','b.eq':'Z','b.ne':'!Z'}.get(op)
        if cond is None:raise ValueError('unmodeled condition '+op)
        stmt=f'if ({cond}) {{pc=0x{dest:x}ULL;break;}}'
    elif op=='bl':
        if len(parts)!=1:raise ValueError('unsupported BL form')
        dest=n(parts[0]);name=plt.get(dest)
        if name=='rand':
            stmt='r[0]=uint32_t(std::rand());'
        elif name=='__stack_chk_fail':
            stmt='throw std::runtime_error("stack check failed");'
        elif dest in sites:
            stmt=f'r[30]=0x{pc+4:x}ULL;pc=0x{dest:x}ULL;break;'
        else:raise ValueError(f'unknown external or uncompiled internal BL {hex(dest)} {name}')
    elif op=='ret':
        if parts and parts!=['x30']:raise ValueError('nonstandard return target')
        stmt='if(r[30]==return_sentinel) return; pc=r[30];break;'
    elif op=='ubfiz':
        if len(parts)!=4:raise ValueError('ubfiz operands')
        shift,width=n(parts[2]),n(parts[3]);
        if not 0<width<=32 or shift<0 or shift+width>64:raise ValueError('unknown bitfield')
        stmt=assign(parts[0],f'(({rx(parts[1])} & 0x{(1<<width)-1:x}ULL) << {shift})')
    elif op in ('lsl','asr'):
        if len(parts)!=3:raise ValueError('shift operands')
        bits=32 if parts[0].startswith('w') else 64
        shift=n(parts[2]);
        if shift<0 or shift>=bits:raise ValueError('illegal shift')
        exp=(f'({rx(parts[1])} << {shift})' if op=='lsl' else
             f'(static_cast<uint64_t>(static_cast<int{bits}_t>({rx(parts[1])}) >> {shift}))')
        stmt=assign(parts[0],exp)
    elif op=='udiv':
        if len(parts)!=3:raise ValueError('udiv operands')
        numer,denom=rx(parts[1]),rx(parts[2]);stmt=assign(parts[0],f'(({denom}) ? ({numer} / {denom}) : 0ULL)')
    elif op=='msub':
        if len(parts)!=4:raise ValueError('msub operands')
        stmt=assign(parts[0],f'({rx(parts[3])} - ({rx(parts[1])} * {rx(parts[2])}))')
    elif op=='smull':
        if len(parts)!=3 or not all(p.startswith('w') for p in parts[1:]):raise ValueError('smull operands')
        stmt=assign(parts[0],f'uint64_t(int64_t(int32_t(uint32_t({rx(parts[1])}))) * int64_t(int32_t(uint32_t({rx(parts[2])}))))')
    elif op=='csel':
        if len(parts)!=4:raise ValueError('csel operands')
        cond={'eq':'Z','ne':'!Z'}.get(parts[3]);
        if not cond:raise ValueError('unsupported select predicate')
        stmt=assign(parts[0],f'(({cond}) ? {rx(parts[1])} : {rx(parts[2])})')
    else:raise ValueError(f'unsupported opcode {hex(pc)} {op} {args}')
    return f'    case 0x{pc:x}ULL: {{ {stmt} pc={nextpc};break; }}'


def select_pair(elf):
    scan=analyze(elf)
    entries=sorted(int(row['address'],16) for row in scan['candidate_entries'])
    end=int(scan['text_address'],16)+scan['text_size_bytes']
    plt=plt_symbols(elf)
    rand_stubs={p for p,name in plt.items() if name=='rand'}
    if not rand_stubs:raise ValueError('stripped ELF has no named libc rand import')
    funcs={}
    for i,entry in enumerate(entries):
        nxt=entries[i+1] if i+1<len(entries) else end
        if nxt<=entry or nxt-entry>2048:continue
        try:funcs[entry]=parse_instructions(elf,entry,nxt)
        except ValueError:continue
    rand_cands=[]
    for entry,rows in funcs.items():
        calls=[n(arg) for _,op,arg in rows if op=='bl' and NUM.fullmatch(arg)]
        if len([c for c in calls if c in rand_stubs])==2 and rows[0][1]=='sub' and rows[0][2].startswith('sp, sp,'):
            rand_cands.append(entry)
    if len(rand_cands)!=1:raise ValueError(f'ambiguous rand-dependent stack functions: {[hex(x) for x in rand_cands]}')
    leaf=rand_cands[0]
    callers=[]
    for entry,rows in funcs.items():
        if entry==leaf:continue
        calls=[n(arg) for _,op,arg in rows if op=='bl' and NUM.fullmatch(arg)]
        if calls==[leaf,leaf] and rows[0][1]=='stp' and rows[-1][1]=='ret':callers.append(entry)
    if len(callers)!=1:raise ValueError('expected one source-blind caller invoking discovered rand leaf twice')
    return scan,plt,funcs,leaf,callers[0]


def locate_guard_got(elf):
    # This metadata survives stripping; do not consult game symbol table or source.
    info = subprocess.run(['readelf','-rW',str(elf)], capture_output=True,
                          text=True, timeout=20, check=True).stdout
    addresses=[]
    for line in info.splitlines():
        if 'R_AARCH64_GLOB_DAT' not in line or '__stack_chk_guard' not in line:
            continue
        m=re.match(r'^\s*([0-9a-fA-F]{8,16})\s+',line)
        if m:addresses.append(int(m[1],16))
    if len(addresses)!=1:
        raise ValueError('requires exactly one dynamic __stack_chk_guard GOT relocation')
    return addresses[0]


def generate(elf):
    scan,plt,funcs,leaf,caller=select_pair(elf)
    guard_got=locate_guard_got(elf)
    # Decode and validate every instruction in both intervals before emission.
    site_map={pc for entry in (leaf,caller) for pc,_,_ in funcs[entry]}
    instructions=[]
    for entry in (leaf,caller):
        for pc,op,args in funcs[entry]:
            if op not in ALLOWED:raise ValueError(f'unsupported ARM64 {hex(pc)} {op}')
            instructions.append(lower(pc,op,args,site_map,plt,guard_got))
    cxx='''// Generated ONLY from ELF64 AArch64 stripped code and import/relocation data.
// AArch64 register + frame lowering, not the original source code.
#include <array>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <stdexcept>
namespace edgeai_blind {
static void run(uint64_t start,uint32_t* board) {
 if(!board) throw std::invalid_argument("board pointer is null");
 uint64_t r[31]={};
 bool Z=false,N=false,C=false,V=false;
 constexpr uint64_t return_sentinel=0xffffffffffffffffULL;
 constexpr uint64_t stack_origin=0x600000000000ULL;
 constexpr uint64_t canary_addr=0x700000000000ULL;
 constexpr uint64_t canary_value=0x178af371b96c5241ULL;
 std::array<uint8_t,4096> stack{};
 uint64_t sp=stack_origin+2048ULL;
 uint64_t board_origin=uint64_t(uintptr_t(board));
 r[0]=board_origin;r[30]=return_sentinel;
 auto read=[&](uint64_t addr,unsigned width)->uint64_t {
  uint64_t value=0;
  if(addr>=stack_origin && addr-stack_origin<=stack.size()-width) {
   std::memcpy(&value,stack.data()+size_t(addr-stack_origin),width);return value;
  }
  if(addr>=board_origin && addr-board_origin<=64-width) {
   std::memcpy(&value,reinterpret_cast<const void*>(uintptr_t(addr)),width);return value;
  }
  if(addr==canary_addr && width==8)return canary_value;
  if(addr==GUARD_GOT_PLACEHOLDER && width==8)return canary_addr;
  throw std::out_of_range("ARM64 memory load outside modeled stack, board or GOT");
 };
 auto write=[&](uint64_t addr,unsigned width,uint64_t value) {
  if(addr>=stack_origin && addr-stack_origin<=stack.size()-width) {
   std::memcpy(stack.data()+size_t(addr-stack_origin),&value,width);return;
  }
  if(addr>=board_origin && addr-board_origin<=64-width) {
   std::memcpy(reinterpret_cast<void*>(uintptr_t(addr)),&value,width);return;
  }
  throw std::out_of_range("ARM64 memory store outside modeled stack and board");
 };
 uint64_t pc=start;
 uint64_t instruction_budget=0;
 for(;;) {
  if(++instruction_budget>1000000ULL)throw std::runtime_error("ARM64 execution budget exceeded");
  switch(pc) {
'''+ '\n'.join(instructions)+'''
    default:throw std::runtime_error("unexpected program counter");
  }
 }
}
}
'''
    cxx=cxx.replace('GUARD_GOT_PLACEHOLDER',f'0x{guard_got:x}ULL')
    cxx_leaf=cxx+f'extern "C" void recovered_{leaf:x}(uint32_t* board) {{edgeai_blind::run(0x{leaf:x}ULL,board);}}\n'
    cxx_caller=f'#include <cstdint>\nextern "C" void edgeai_run_{leaf:x}(uint32_t*);\n'
    # dispatch export is provided by the leaf translation unit; caller is thin ABI entry wrapper.
    cxx_leaf+=f'extern "C" void edgeai_run_{leaf:x}(uint32_t* board) {{edgeai_blind::run(0x{caller:x}ULL,board);}}\n'
    cxx_caller+=f'extern "C" void recovered_{caller:x}(uint32_t* board) {{edgeai_run_{leaf:x}(board);}}\n'
    return (leaf,caller,cxx_leaf,cxx_caller,{
        'binary_sha256':scan['input_sha256'], 'source_read':False, 'symbols_used':False,
        'rand_plt_derived_from_elf':True,'guard_got_derived_from_elf_relocation':hex(guard_got),'function_names_recovered':False,
        'callee_entry':hex(leaf),'caller_entry':hex(caller),
        'callee_instructions':len(funcs[leaf]),'caller_instructions':len(funcs[caller]),
        'ABI_assumption':'void(uint32_t board[16])',
        'implementation':'explicit ARM64 instruction-semantics lowering into C++ VM',
        'behavioral_equivalence_proven':False,
        'remaining_limitations':['Fixed board size and parameter ABI assumptions.',
          'Stack-check guard GOT extracted from the dynamic relocation table.',
          'Only rand and stack-check fail imports supported for these two functions.']})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args()
    leaf,caller,cpp_leaf,cpp_caller,report=generate(a.elf)
    a.output_dir.mkdir(parents=True,exist_ok=True)
    (a.output_dir/f'candidate_{leaf:x}.cpp').write_text(cpp_leaf)
    (a.output_dir/f'candidate_{caller:x}.cpp').write_text(cpp_caller)
    (a.output_dir/'stack_rand_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
