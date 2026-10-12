#!/usr/bin/env python3
"""Recover winner() from stripped ARM32 ELF across Clang -O1/-O2/-O3/-Os/-Oz.

Pattern-constrained and fail-closed; not a generic decompiler.
"""
import argparse
import json
from pathlib import Path
import re
import struct
from recover_winner import composed_address, emit_cpp
from recover_winner_stripped import load_segments, memory_region, disassembled_instructions, recover_stripped

REG_TABLE='r12'
REG_BOARD='lr'
PUSH=('push','{r4, r10, r11, lr}')
POP=('pop','{r4, r10, r11, pc}')
TABLE_READS={
    ('ldrb','r0, [r2, r0]!'),
    ('ldrb','r3, [r2, #0x1]'),
    ('ldrb','r4, [r2, #0x2]'),
}
BOARD_READS={
    ('ldr','r0, [lr, r0, lsl #2]'),
    ('ldr','r2, [lr, r3, lsl #2]'),
    ('ldr','r3, [lr, r4, lsl #2]'),
}

def branch_target(row):
    match=re.match(r'^0x([0-9a-fA-F]+)',row['args'])
    return int(match[1],16) if match else None

def base_register_address(data,segments,rows,register):
    try:
        return composed_address(rows,register),'movw_movt'
    except ValueError:
        pass
    pc_loads=[row for row in rows if row['op']=='ldr' and
              re.fullmatch(re.escape(register)+r', \[pc, #(0x[0-9a-fA-F]+|\d+)\]',row['args'])]
    if len(pc_loads)!=1:
        raise ValueError('unsupported or ambiguous PC-relative pointer for '+register)
    ins=pc_loads[0]
    offset=int(ins['args'].split('#')[1].split(']')[0],0)
    if offset%4 or offset>4095:
        raise ValueError('invalid literal displacement')
    literal_address=ins['pc']+8+offset
    literal=memory_region(data,segments,literal_address,4,4,True)
    return struct.unpack('<I',literal)[0],'pc_literal'

def verify_candidate(data,segments,rows):
    if len(rows)<22 or (rows[0]['op'],rows[0]['args'])!=PUSH:
        raise ValueError('not a supported -Os/-Oz prologue')
    if any(b['pc']!=a['pc']+4 for a,b in zip(rows,rows[1:])):
        raise ValueError('noncontiguous instruction candidate')
    bypc={x['pc']:x for x in rows}
    signatures={(x['op'],x['args']) for x in rows}
    if not TABLE_READS.issubset(signatures) or not BOARD_READS.issubset(signatures):
        raise ValueError('expected indexed table and board reads missing')
    for key in [('add','r0, r1, r1, lsl #1'),('mov','r2, r12'),
                ('cmp','r0, #0'),('cmp','r0, r2'),('cmpeq','r2, r3'),
                ('mov','r0, #0')]:
        if key not in signatures:
            raise ValueError('missing loop or three-way equality predicate')
    table_address,table_source=base_register_address(data,segments,rows,REG_TABLE)
    board_address,board_source=base_register_address(data,segments,rows,REG_BOARD)
    table_positions=sorted(x['pc'] for x in rows if (x['op'],x['args']) in TABLE_READS)
    board_positions=sorted(x['pc'] for x in rows if (x['op'],x['args']) in BOARD_READS)
    if len(table_positions)!=3 or len(board_positions)!=3:
        raise ValueError('ambiguous table or board load count')
    if not table_positions[0]<board_positions[-1]:
        raise ValueError('unexpected table / board ordering')
    loop_starts=[x['pc'] for x in rows if (x['op'],x['args'])==('add','r0, r1, r1, lsl #1')]
    if len(loop_starts)!=1:
        raise ValueError('ambiguous loop body')
    loop_start=loop_starts[0]
    bounds=[x for x in rows if x['op']=='cmp' and re.fullmatch(r'r1, #(0x[0-9a-fA-F]+|\d+)',x['args'])]
    if len(bounds)!=1:
        raise ValueError('ambiguous loop bound')
    count=int(bounds[0]['args'].split('#')[1],0)
    if not 1<=count<=256:
        raise ValueError('unsupported table length')
    pops=[x for x in rows if (x['op'],x['args'])==POP]
    if not pops or (rows[-1]['op'],rows[-1]['args'])!=POP:
        raise ValueError('no recognized return epilogue')
    if bounds[0]['pc']>loop_start:
        optimization='Os'
        if len(pops)!=1 or not any(x['op']=='bne' and branch_target(x)==loop_start for x in rows):
            raise ValueError('unsupported -Os loop back edge')
        early=[x for x in rows if x['op']=='beq' and branch_target(x)==pops[0]['pc']]
        if len(early)!=1:
            raise ValueError('unsupported -Os early success exit')
        zero_check=next((i for i in rows if (i['op'],i['args'])==('cmp','r0, #0')),None)
        equal_check=next((i for i in rows if (i['op'],i['args'])==('cmpeq','r2, r3')),None)
        retry_pc=next((i['pc'] for i in rows if (i['op'],i['args'])==('add','r1, r1, #1')),None)
        zero_branch=bypc.get(zero_check['pc']+4,{}) if zero_check else {}
        equal_branch=bypc.get(equal_check['pc']+4,{}) if equal_check else {}
        if not retry_pc or zero_branch.get('op')!='beq' or branch_target(zero_branch)!=retry_pc:
            raise ValueError('zero-board-value retry path not proven')
        if equal_branch.get('op')!='beq' or branch_target(equal_branch)!=pops[0]['pc']:
            raise ValueError('equality success return not proven')
    else:
        optimization='Oz'
        if len(pops)!=2 or not any(x['op']=='beq' and branch_target(x)==pops[1]['pc']-4 for x in rows):
            raise ValueError('unsupported -Oz loop bound exit')
        back=[x for x in rows if x['op'] in ('bne','beq') and branch_target(x)==bounds[0]['pc']]
        if len(back)!=2 or {x['op'] for x in back}!={'bne','beq'}:
            raise ValueError('unsupported -Oz retry logic')
        zero_check=next((i for i in rows if (i['op'],i['args'])==('cmp','r0, #0')),None)
        equal_check=next((i for i in rows if (i['op'],i['args'])==('cmpeq','r2, r3')),None)
        if not zero_check or not equal_check:
            raise ValueError('missing -Oz equality guards')
        zero_retry=bypc.get(zero_check['pc']+12,{})
        equal_retry=bypc.get(equal_check['pc']+4,{})
        if zero_retry.get('op')!='beq' or branch_target(zero_retry)!=bounds[0]['pc']:
            raise ValueError('zero-board retry path not proven')
        if equal_retry.get('op')!='bne' or branch_target(equal_retry)!=bounds[0]['pc']:
            raise ValueError('unequal-board retry path not proven')
        if bypc.get(pops[0]['pc']+4,{}).get('op')!='mov' or bypc[pops[0]['pc']+4]['args']!='r0, #0':
            raise ValueError('zero fallback not guarded by success return')
    table_bytes=memory_region(data,segments,table_address,3*count,4,True)
    triplets=[list(table_bytes[i:i+3]) for i in range(0,len(table_bytes),3)]
    board_cells=max(max(row) for row in triplets)+1
    if board_cells>4096:
        raise ValueError('inferred board size out of supported range')
    memory_region(data,segments,board_address,board_cells*4,2,False)
    return {
        'function':'winner','source':'stripped ARM ELF PT_LOAD and validated optimized loop fingerprint',
        'optimization_pattern':optimization,'function_address':hex(rows[0]['pc']),
        'board_address':hex(board_address),'board_cells':board_cells,
        'table_address':hex(table_address),'table_symbol':None,
        'pointer_origins':{'table':table_source,'board':board_source},
        'triplets':triplets,'loop_iterations':count,
        'board_load_pcs':[hex(x) for x in board_positions],
        'table_load_pcs':[hex(x) for x in table_positions],
        'boolean_test':'validated_cmp_cmpeq_branch_pattern',
        'constraints':[
            'Recognizes clang -Os or -Oz ARM32 winner loop; not generic decompilation',
            'Requires ELF loadable segments; no ELF symbol names required',
            'Generated C++ control structure and prototype remain pattern-supplied',
            'Board capacity inferred from maximum table index'
        ]
    }

BOARD_OFFSET=re.compile(r'^(r0|r2|r3), \[r1(?:, #(0x[0-9a-fA-F]+|\d+))?\]$')

def verify_unrolled(data,segments,rows):
    """Recognize Clang -O2/-O3 direct 8*3 board loads and guarded exits."""
    if len(rows)<65 or rows[0]['op']!='movw' or not rows[0]['args'].startswith('r1, #'):
        raise ValueError('not an unrolled winner entry')
    if rows[1]['op']!='movt' or not rows[1]['args'].startswith('r1, #'):
        raise ValueError('no second half of board address')
    if (rows[-1]['op'],rows[-1]['args'])!=('bx','lr'):
        raise ValueError('unrolled function exit missing')
    if any(b['pc']!=a['pc']+4 for a,b in zip(rows,rows[1:])):
        raise ValueError('noncontiguous unrolled candidate')
    base=composed_address(rows,'r1')
    indexed=[]
    for k,ins in enumerate(rows):
        if ins['op']!='ldr':
            continue
        m=BOARD_OFFSET.fullmatch(ins['args'])
        if m:
            offset=int(m[2],0) if m[2] else 0
            if offset%4 or offset>=16384:
                raise ValueError('invalid board load offset')
            indexed.append((k,m[1],offset//4))
    if len(indexed)!=24:
        raise ValueError('expected 24 direct indexed board loads')
    triplets=[]
    shared_return=None
    for group in range(8):
        part=indexed[group*3:group*3+3]
        if any(b[0]!=a[0]+1 for a,b in zip(part,part[1:])):
            raise ValueError('nonadjacent board accesses')
        next_index=indexed[(group+1)*3][0] if group<7 else None
        registers=[x[1] for x in part]
        if group<7 and registers!=['r0','r2','r3']:
            raise ValueError('unexpected board value register order')
        if group==7 and registers!=['r2','r3','r0']:
            raise ValueError('unsupported final diagonal register order')
        triplets.append([item[2] for item in part])
        after=part[-1][0]+1
        if group<7:
            if [(x['op'],x['args']) for x in rows[after:after+1]]!=[('cmp','r0, #0')]:
                raise ValueError('nonzero guard missing')
            zero_branch=rows[after+1]
            if zero_branch['op']!='beq' or branch_target(zero_branch)!=rows[next_index]['pc']:
                raise ValueError('zero guard does not skip to next triplet')
            if [(x['op'],x['args']) for x in rows[after+2:after+4]]!=[
                ('cmp','r0, r2'),('cmpeq','r2, r3')]:
                raise ValueError('three-way equality check missing')
            equality_branch=rows[after+4]
            if group==0:
                if equality_branch['op']!='bne' or branch_target(equality_branch)!=rows[next_index]['pc']:
                    raise ValueError('first unequal case not retried')
                if (rows[after+5]['op'],rows[after+5]['args'])!=('bx','lr'):
                    raise ValueError('first success return missing')
                shared_return=rows[after+5]['pc']
            elif group==6:
                if (equality_branch['op'],equality_branch['args'])!=('bxeq','lr'):
                    raise ValueError('penultimate win return missing')
            else:
                if equality_branch['op']!='beq' or branch_target(equality_branch)!=shared_return:
                    raise ValueError('matching triplets must return the first value')
        else:
            last=[(row['op'],row['args']) for row in rows[after:]]
            expected=[('cmp','r3, r0'),('mov','r0, r2'),('movwne','r0, #0x0'),
                      ('cmp','r2, r3'),('movwne','r0, #0x0'),
                      ('cmp','r2, #0'),('moveq','r0, r2'),('bx','lr')]
            if last!=expected:
                raise ValueError('final diagonal guard not supported')
    board_cells=max(max(row) for row in triplets)+1
    if board_cells>4096:
        raise ValueError('inferred board too large')
    memory_region(data,segments,base,4*board_cells,2,False)
    return {
        'function':'winner','source':'stripped ARM ELF and fully unrolled static-load fingerprint',
        'optimization_pattern':'O2_or_O3','function_address':hex(rows[0]['pc']),
        'board_address':hex(base),'board_cells':board_cells,
        'table_address':None,'table_symbol':None,
        'triplets':triplets,'loop_iterations':len(triplets),
        'board_load_pcs':[hex(rows[x[0]]['pc']) for x in indexed],
        'table_load_pcs':[],'boolean_test':'unrolled_arm_cmp_cmpeq_with_early_returns',
        'constraints':['Recognizes clang ARM -O2/-O3 fingerprint without a data table',
                       'Matches all 24 board reads plus branch/return semantics',
                       'Still uses supplied C++ loop/equality skeleton, not general recovery']
    }

def recover_unrolled(data,segments,rows):
    matches=[]
    for i,ins in enumerate(rows):
        if ins['op']!='movw' or not ins['args'].startswith('r1, #'):
            continue
        for j in range(i+65,min(i+140,len(rows))):
            if (rows[j]['op'],rows[j]['args'])!=('bx','lr'):
                continue
            try:
                candidate=verify_unrolled(data,segments,rows[i:j+1])
            except (ValueError,IndexError):
                continue
            matches.append(candidate)
            break
    if len(matches)!=1:
        raise ValueError('no unique recognized unrolled winner')
    return matches[0]

def recover_variants(path):
    path=Path(path)
    try:
        original=recover_stripped(path)
    except ValueError:
        original=None
    if original is not None:
        original['optimization_pattern']='O1'
        return original
    data=path.read_bytes()
    segments=load_segments(data)
    rows=disassembled_instructions(path)
    matches=[]
    for i,ins in enumerate(rows):
        if (ins['op'],ins['args'])!=PUSH:
            continue
        for j in range(i+20,min(i+75,len(rows))):
            if (rows[j]['op'],rows[j]['args'])!=POP:
                continue
            end_candidates=[j]
            for k in range(j+1,min(j+5,len(rows))):
                if (rows[k]['op'],rows[k]['args'])==POP:
                    end_candidates.append(k)
                    break
            for end in end_candidates:
                try:
                    candidate=verify_candidate(data,segments,rows[i:end+1])
                except ValueError:
                    continue
                matches.append(candidate)
                break
            if matches and matches[-1]['function_address']==hex(ins['pc']):
                break
    if len(matches)==1:
        return matches[0]
    if len(matches)>1:
        raise ValueError('ambiguous optimized winner loops')
    return recover_unrolled(data,segments,rows)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--cpp',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    report=recover_variants(args.elf)
    args.cpp.parent.mkdir(parents=True,exist_ok=True)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.cpp.write_text(emit_cpp(report),encoding='utf-8')
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pattern':report['optimization_pattern'],'triplets':report['loop_iterations'],'cpp':str(args.cpp)}))

if __name__=='__main__':
    main()
