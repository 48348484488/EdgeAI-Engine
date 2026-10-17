#!/usr/bin/env python3
"""ELF-only AArch64 step validator against real QEMU CPU-state snapshots.

The original ARM64 .text bytes are decoded by llvm-objdump. A small
fail-closed integer/branch interpreter is checked *at each PC* against QEMU
state from the original unmodified ELF. Address-space differences for the
bounded input buffer are normalized. Unknown opcodes reject the test.
"""
import argparse, hashlib, json, re, subprocess
from pathlib import Path

INS=re.compile(r'^\s*([0-9a-fA-F]+):\s+([a-z][a-z0-9.]*)\s*(.*?)\s*$')
REG=re.compile(r'^[wx](\d{1,2})$')
MEM=re.compile(r'^(w\d+), \[(x\d+), (x\d+), lsl #(\d+)\]$')
MASK32=(1<<32)-1
MASK64=(1<<64)-1
VBASE=0x10000000


def disassemble(elf,start,end):
    if end<=start or end-start>4096 or (start|end)&3:
        raise ValueError('out-of-budget ELF code interval')
    proc=subprocess.run(['llvm-objdump','-d','--no-show-raw-insn',
        '--start-address='+hex(start),'--stop-address='+hex(end),str(elf)],
        capture_output=True,text=True,check=True,timeout=20)
    out={}
    for line in proc.stdout.splitlines():
        m=INS.match(line)
        if m and start<=int(m[1],16)<end:
            pc=int(m[1],16)
            out[pc]=(m[2],re.sub(r'\s+<[^>]+>$','',m[3].split('//',1)[0].strip()))
    if set(out)!=set(range(start,end,4)):
        raise ValueError('incomplete/overlapping instructions')
    return out


def run_interpreter(code,start,board,*,invert_equal=False,budget=4096):
    if len(board)!=16:raise ValueError('exactly 16 input words required')
    regs=[0]*31;regs[0]=VBASE
    defined={0};flags=None;pc=start;history=[]
    def get(arg):
        if arg.startswith('#'):return int(arg[1:],0)
        m=REG.fullmatch(arg)
        if not m or int(m[1])>=31:raise ValueError('invalid operand '+arg)
        x=regs[int(m[1])]
        return x&MASK32 if arg[0]=='w' else x
    def put(dest,val):
        m=REG.fullmatch(dest)
        if not m or int(m[1])>=31:raise ValueError('invalid destination '+dest)
        i=int(m[1])
        regs[i]=val&(MASK32 if dest[0]=='w' else MASK64)
        defined.add(i)
    for _ in range(budget):
        if pc not in code:raise ValueError('branch outside bounded ELF function')
        op,args=code[pc];pieces=[x.strip() for x in args.split(',')]
        history.append({'pc':hex(pc),
            'defined':{f'X{i:02}':regs[i] for i in sorted(defined)},
            'nzcv':flags})
        nxt=pc+4
        if op=='add' and len(pieces)==3:
            put(pieces[0],get(pieces[1])+get(pieces[2]))
        elif op=='mov' and len(pieces)==2:
            put(pieces[0],get(pieces[1]))
        elif op=='ldr':
            m=MEM.fullmatch(args)
            if not m or int(m[4]) not in (0,2):
                raise ValueError('unmodeled ARM64 memory load: '+args)
            addr=get(m[2])+(get(m[3])<<int(m[4]))
            if addr<VBASE or addr>VBASE+60 or (addr-VBASE)%4:
                raise ValueError('memory outside input board')
            put(m[1],board[(addr-VBASE)//4])
        elif op=='cmp' and len(pieces)==2:
            width=32 if pieces[0].startswith('w') else 64
            mask=(1<<width)-1
            a=get(pieces[0])&mask;b=get(pieces[1])&mask
            d=(a-b)&mask
            n=(d>>(width-1))&1;z=int(d==0);c=int(a>=b)
            v=int(bool(((a^b)&(a^d))&(1<<(width-1))))
            flags=(n<<3)|(z<<2)|(c<<1)|v
        elif op=='b' and len(pieces)==1:
            nxt=int(pieces[0],0)
        elif op in ('b.eq','b.ne') and len(pieces)==1:
            if flags is None:raise ValueError('branch before defined compare flags')
            z=bool(flags&4)
            take=z if op=='b.eq' else not z
            if invert_equal and op=='b.eq':take=not take
            if take:nxt=int(pieces[0],0)
        elif op=='ret' and args in ('','x30'):
            return history,regs[0]&MASK32
        else:
            raise ValueError(f'unknown ARM64 instruction {hex(pc)} {op} {args}')
        pc=nxt
    raise ValueError('simulator exceeded instruction budget')


def compare(elf,qemu_json,raw_trace,start,end,case,*,invert_equal=False):
    record=json.loads(Path(qemu_json).read_text())
    snapshots=record['snapshot_sequence']
    if hashlib.sha256(Path(raw_trace).read_bytes()).hexdigest()!=record['qemu_raw_trace_sha256']:
        raise ValueError('real QEMU raw trace SHA256 mismatch')
    info=record['original_machine_io']
    if info['case']!=case or len(info['input_board'])!=16:
        raise ValueError('QEMU input record inconsistent')
    if not snapshots or int(snapshots[0]['pc'],16)!=start:
        raise ValueError('real QEMU did not start at expected ELF entry')
    states,retval=run_interpreter(disassemble(elf,start,end),start,info['input_board'],
                                  invert_equal=invert_equal)
    base=int(snapshots[0]['regs']['X00'],16)
    counts={'pc':0,'registers':0,'nzcv':0}
    first=None
    for step in range(max(len(states),len(snapshots))):
        if step>=len(states) or step>=len(snapshots):
            first={'step':step,'kind':'instruction_count',
                   'real':len(snapshots),'simulated':len(states)}
            break
        a=snapshots[step];b=states[step]
        if a['pc']!=b['pc']:
            first={'step':step,'kind':'PC','real':a['pc'],'simulated':b['pc']}
            break
        counts['pc']+=1
        for reg,val in b['defined'].items():
            seen=int(a['regs'][reg],16)
            if base<=seen<=base+64:
                seen=VBASE+(seen-base)
            if seen!=val:
                first={'step':step,'kind':'register','pc':a['pc'],'reg':reg,
                       'real':hex(seen),'simulated':hex(val)}
                break
            counts['registers']+=1
        if first:break
        if b['nzcv'] is not None:
            actual=(int(a['pstate'],16)>>28)&15
            if actual!=b['nzcv']:
                first={'step':step,'kind':'NZCV','pc':a['pc'],
                       'real':hex(actual),'simulated':hex(b['nzcv'])}
                break
            counts['nzcv']+=1
    if not first and retval!=info['actual_original_return']:
        first={'step':len(states),'kind':'return_value',
               'real':info['actual_original_return'],'simulated':retval}
    return {'case':case,'entry':hex(start),'ELF_sha256':hashlib.sha256(Path(elf).read_bytes()).hexdigest(),
        'executed_real_original_ARM64_QEMU':True,'original_game_source_read':False,
        'real_cpu_steps':len(snapshots),'simulator_steps':len(states),
        'checks':counts,'checks_total':sum(counts.values()),
        'passed':first is None,'first_mismatch':first,
        'mutation_injected':invert_equal,
        'limitations':['QEMU genuine CPU snapshots vs bounded interpreter, not C++ equivalence',
                       'Only integer/word-load subset; unsupported operations reject',
                       'Sampled original inputs do not establish universal equivalence']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--cpu',type=Path,required=True)
    p.add_argument('--raw',type=Path,required=True)
    p.add_argument('--entry',type=lambda x:int(x,0),required=True)
    p.add_argument('--stop',type=lambda x:int(x,0),required=True)
    p.add_argument('--case',type=int,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--invert-equal',action='store_true')
    a=p.parse_args()
    result=compare(a.elf,a.cpu,a.raw,a.entry,a.stop,a.case,invert_equal=a.invert_equal)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if a.invert_equal and result['passed']:raise SystemExit('test expected an injected mismatch')
    if not a.invert_equal and not result['passed']:raise SystemExit('real ARM64 machine state disagrees with interpreter')


if __name__=='__main__':main()
