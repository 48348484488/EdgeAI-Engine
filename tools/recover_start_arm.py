"""Recover simple scripted ARM32 game start() call sequences from LLVM disassembly.

Recognizes a narrow compiler fingerprint only. Does not read source to generate.
"""
import re
import subprocess
import json
from pathlib import Path

HEAD=re.compile(r'^([0-9a-fA-F]+) <(\w+)>:$')
LINE=re.compile(r'^\s*([0-9a-fA-F]+):\s+(\w+)\s*(.*)$')
IMM=re.compile(r'^r([01]),\s*#(0x[0-9a-fA-F]+|\d+)$')
TARGET=re.compile(r'^0x([0-9a-fA-F]+)(?:\s+<.*>)?$')


def recover_text(disassembly):
    active=False; seen=False; play=None; rows=[]
    for raw in disassembly.splitlines():
        head=HEAD.fullmatch(raw.strip())
        if head:
            if head[2]=='start':
                if seen: raise ValueError('duplicate start')
                seen=active=True
            else:
                if head[2]=='play':
                    if play is not None: raise ValueError('duplicate play')
                    play=int(head[1],16)
                active=False
            continue
        if active:
            m=LINE.match(raw)
            if m:
                rows.append((int(m[1],16),m[2],m[3].split('@')[0].strip()))
    if not seen or play is None or not 7<=len(rows)<=128:
        raise ValueError('unrecognized game start/play')
    if rows[:2]!=[(rows[0][0],'push','{r11, lr}'),(rows[0][0]+4,'mov','r11, sp')]:
        raise ValueError('unsupported prologue')
    if any(b[0]!=a[0]+4 for a,b in zip(rows,rows[1:])):
        raise ValueError('noncontiguous ARM body')
    if rows[-2][1:]!=('pop','{r11, lr}') or rows[-1][1]!='b':
        raise ValueError('unsupported epilogue')
    i=2; moves=[]
    while i<len(rows):
        if i+2>=len(rows): raise ValueError('missing pair or call')
        m0=IMM.fullmatch(rows[i][2]) if rows[i][1]=='mov' else None
        m1=IMM.fullmatch(rows[i+1][2]) if rows[i+1][1]=='mov' else None
        if not m0 or not m1 or m0[1]!='0' or m1[1]!='1':
            raise ValueError('unrecognized call arguments')
        a,b=int(m0[2],0),int(m1[2],0)
        if not 0<=a<=65535 or not 0<=b<=65535:
            raise ValueError('unsupported immediate value')
        final=(i+2==len(rows)-2)
        if final:
            if rows[i+2][1:]!=('pop','{r11, lr}'):
                raise ValueError('missing pop')
            call=rows[i+3]
        else:
            call=rows[i+2]
        if call[1] != ('b' if final else 'bl'):
            raise ValueError('unsupported call')
        target=TARGET.fullmatch(call[2])
        if not target or int(target[1],16)!=play:
            raise ValueError('unexpected call target')
        moves.append({'position':a,'player':b,'pc':hex(call[0]),'tail':final})
        i+=4 if final else 3
        if final: break
    if i!=len(rows) or not moves or not moves[-1]['tail']:
        raise ValueError('unconsumed instructions')
    return {'function':'start','pattern':'straight_line_ARM32_calls',
            'moves':moves,'play_pc':hex(play), 'instructions':len(rows),
            'source_read':False,'runtime_proven':False,
            'template_assumptions':['start() and play(int,int) signatures',
                                    'no hidden callee effects beyond real play']}


def recover_elf(elf):
    s=subprocess.run(['llvm-objdump','--no-show-raw-insn','-d',str(elf)],
                     capture_output=True,text=True,check=True,timeout=20).stdout
    return recover_text(s)


def emit_cpp(report):
    if report['pattern']!='straight_line_ARM32_calls': raise ValueError('unverified')
    lines=['extern "C" int play(int, int);','extern "C" int start(void) {']
    for move in report['moves'][:-1]:
        lines.append('    (void)play(%d, %d);'%(move['position'],move['player']))
    last=report['moves'][-1]
    lines.append('    return play(%d, %d);'%(last['position'],last['player']))
    return '\n'.join(lines+['}',''])


if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument('elf',type=Path)
    ap.add_argument('--cpp',type=Path,required=True)
    ap.add_argument('--report',type=Path,required=True)
    args=ap.parse_args()
    result=recover_elf(args.elf)
    args.cpp.parent.mkdir(parents=True,exist_ok=True)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.cpp.write_text(emit_cpp(result))
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'moves':len(result['moves']),'source_read':False}))
