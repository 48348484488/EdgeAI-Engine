#!/usr/bin/env python3
"""Trace lexical ADRP/ADD origins of AArch64 indexed-dispatch table-base registers.

This is deliberately a static hint report, not sound reaching-definitions analysis:
a preceding instruction in an ELF text listing is not necessarily executed.
No original program code is run, no jump-table bytes are read, and no
indirect targets are promoted to resolved without separate verified bounds.
"""
import argparse
import json
import re
from pathlib import Path

LINE = re.compile(r'^\s*([0-9a-fA-F]+):\s+([A-Za-z][A-Za-z0-9.]*)\b(.*?)\s*$')
REGISTER = re.compile(r'^[wx]([0-9]|[12][0-9]|30)$')
ADRP = re.compile(r'^x([0-9]|[12][0-9]|30),\s*(0x[0-9a-fA-F]+)(?:\s+.*)?$')
IMM_ADD = re.compile(r'^x([0-9]|[12][0-9]|30),\s*x([0-9]|[12][0-9]|30),\s*#(0x[0-9a-fA-F]+|\d+)(?:\s+.*)?$')
NONWRITING = frozenset(('cmp','cmn','tst','str','strb','strh','stur','stp','prfm','nop','hint','ret','br','blr','bl','b','cbz','cbnz','tbz','tbnz'))
MAX_BACKTRACK = 1536


def parse_llvm(text):
    result = {}
    for line in text.splitlines():
        match = LINE.match(line)
        if match:
            pc = int(match[1],16)
            if pc in result or pc%4:
                raise ValueError('duplicate or unaligned LLVM PC')
            result[pc]=(match[2].lower(),match[3].split('//',1)[0].strip())
    return result


def reg_id(operand):
    match=REGISTER.fullmatch(operand.strip())
    return int(match[1]) if match else None


def may_write_register(op,args,reg):
    if op in NONWRITING or op.startswith('b.'):
        return False
    fields=args.split(',',2)
    first=fields[0].strip() if fields else ''
    if reg_id(first)==reg:
        return True
    if op in ('ldp','ldnp') and len(fields)>1 and reg_id(fields[1])==reg:
        return True
    return False


def pair_for_site(pc,reg,code):
    history=[(p,*inst) for p,inst in sorted(code.items()) if p<pc and p>=pc-4*MAX_BACKTRACK]
    writes=[(p,op,args) for p,op,args in history if may_write_register(op,args,reg)]
    if not writes:
        return {'status':'NO_TEXTUAL_ORIGIN','reason':'no_prior_assignment_to_table_base'}
    add_pc,add_op,add_args=writes[-1]
    match=IMM_ADD.fullmatch(add_args) if add_op=='add' else None
    if not match or not (int(match[1])==reg==int(match[2])):
        return {'status':'NO_TEXTUAL_ORIGIN', 'reason':'last_assignment_not_same_register_immediate_add',
                'last_assignment_pc':hex(add_pc)}
    before=[(p,op,args) for p,op,args in writes if p<add_pc]
    if not before:
        return {'status':'NO_TEXTUAL_ORIGIN','reason':'no_prior_ADRP'}
    base_pc,base_op,base_args=before[-1]
    ap=ADRP.fullmatch(base_args) if base_op=='adrp' else None
    if not ap or int(ap[1])!=reg:
        return {'status':'NO_TEXTUAL_ORIGIN','reason':'last_prior_assignment_not_ADRP',
                'last_assignment_pc':hex(base_pc)}
    page=int(ap[2],16)
    offset=int(match[3],0)
    if page%4096 or not 0<=offset<4096:
        return {'status':'NO_TEXTUAL_ORIGIN','reason':'invalid_ADRP_ADD_immediate'}
    span=[(p,op,args) for p,op,args in history if base_pc<p<pc]
    calls=[hex(p) for p,op,args in span if op in ('bl','blr')]
    transfers=[hex(p) for p,op,args in span if op in ('b','br','ret','cbz','cbnz','tbz','tbnz') or op.startswith('b.')]
    volatile = reg<=18 or reg==30
    return {
        'status':'TEXTUAL_ADRP_ADD_CANDIDATE',
        'table_base_register':'x'+str(reg),
        'table_base_candidate':hex(page+offset),
        'adrp_pc':hex(base_pc),'add_pc':hex(add_pc),
        'add_gap_instructions':(add_pc-base_pc)//4-1,
        'distance_add_to_dispatch_instructions':(pc-add_pc)//4,
        'intervening_call_count':len(calls),
        'potential_volatile_call_clobber':volatile and bool(calls),
        'intervening_transfer_count':len(transfers),
        'intervening_transfers_sample':transfers[:12],
        'all_paths_reaching_definition_proven':False,
        'table_bytes_read':False,
        'target_entries_resolved':False,
    }


def analyze(indirect, llvm_disassembly):
    if indirect.get('architecture')!='AArch64' or indirect.get('targets_resolved') is not False:
        raise ValueError('complete unresolved AArch64 dispatch report required')
    code=parse_llvm(llvm_disassembly)
    entry=int(indirect['entry'],16)
    if not 0<indirect.get('indirect_site_count',0)<100:
        raise ValueError('invalid indirect site count')
    results=[]
    for site in indirect['sites']:
        pc=int(site['pc'],16)
        if pc<entry or pc%4 or pc not in code:
            raise ValueError('dispatch PC missing from LLVM disassembly')
        kind=site['pattern']
        row={'pc':hex(pc),'pattern':kind}
        if kind!='pc_relative_indexed_table_dispatch_candidate':
            row.update({'status':'NOT_TABLE_DISPATCH','reason':'non_table_site'})
        else:
            if code[pc][0]!='br':raise ValueError('table site not a BR')
            reg=reg_id(site['table_base_register'])
            if reg is None:raise ValueError('invalid table-base register')
            row.update(pair_for_site(pc,reg,code))
        results.append(row)
    if len(results)!=indirect['indirect_site_count']:
        raise ValueError('site count mismatch')
    return {'status':'AARCH64_TEXTUAL_TABLE_BASE_PROVENANCE_AUDIT',
            'architecture':'AArch64','function':indirect['function'],
            'site_count':len(results),
            'textual_origins_found':sum(x['status']=='TEXTUAL_ADRP_ADD_CANDIDATE' for x in results),
            'textual_origins_with_volatile_call_hazard':sum(x.get('potential_volatile_call_clobber',False) for x in results),
            'sites':results,
            'indirect_targets_resolved':False,'table_bytes_read':False,
            'control_flow_reaching_definitions_proven':False,'original_game_executed':False,
            'limitations':[
                'Lexically preceding instructions may not execute on the same runtime path.',
                'Direct/conditional branch and call locations reported as hazards, not proven dataflow.',
                'AAPCS64 caller-saved registers are conservatively treated as clobberable.',
                'Candidate bases do not establish valid index ranges or target addresses.',
                'No jump table bytes read; no game code executed.'
            ]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('indirect_json',type=Path)
    parser.add_argument('llvm_disassembly',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    report=analyze(json.loads(args.indirect_json.read_text()), args.llvm_disassembly.read_text())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='sites'},indent=2))

if __name__=='__main__':main()
