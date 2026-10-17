#!/usr/bin/env python3
"""Multi-pass blind AArch64 ELF to C++ reconstruction.

Tries every candidate from executable bytes. Reconstructs leaves first,
then ABI-validated direct callers until a fixed point. No symbol table,
upstream source, manually selected function names or game-specific addresses.
Counts *emission*, *compilation* and *behavioral validation* separately.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from aarch64_stripped_discovery import analyze
from aarch64_leaf_lifter import run as read_leaf
from aarch64_mutating_lifter import run as mutable_leaf
from aarch64_scalar_lifter import run as scalar_leaf
from aarch64_multimem_leaf_lifter import run as multimem_leaf
from aarch64_linked_lifter import run as linked_caller
from aarch64_move_caller_lifter import run as move_caller
from aarch64_printf_lifter import run as printf_leaf
from aarch64_static_printf_sequence_lifter import run as static_printf_sequence
from aarch64_stack_vm_lifter import generate as generate_stack_pair

LEAVES=(('read_only_leaf',read_leaf),
        ('mutating_leaf',mutable_leaf),
        ('scalar_leaf',scalar_leaf),
        ('three_arg_memory_leaf',multimem_leaf),
        ('terminal_printf_leaf',printf_leaf),
        ('terminal_static_sequence',static_printf_sequence))


def _evidence(row,typ,src,meta,outdir):
    if meta.get('source_read') is not False or meta.get('symbols_used') is not False:
        raise ValueError('candidate used symbols or original game source')
    if not src or not isinstance(src,str):
        raise ValueError('empty/invalid C++')
    file=f'candidate_{int(row["address"],16):x}.cpp'
    (outdir/file).write_text(src,encoding='utf-8')
    return {'address':row['address'],
            'status':'CPP_EMITTED_NOT_BEHAVIORALLY_VALIDATED',
            'lifter':typ,'file':file,
            'instructions':meta.get('instructions_translated',meta.get('instruction_count')),
            'abi_assumption':meta.get('ABI_assumption',
                meta.get('assumed_abi',
                    meta.get('known_abi_assumption',meta.get('return_abi_assumption')))),
            'attempt_failures':row.get('attempt_failures',[])}


def run(elf,output,compile_cpp=True):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    scan=analyze(elf)
    if scan.get('symbols_used') is not False or scan.get('source_read') is not False:
        raise ValueError('not stripped source-blind scan')
    candidates={int(item['address'],16):
       {'address':item['address'],'status':'UNSUPPORTED','attempt_failures':[]}
       for item in scan['candidate_entries']}
    # Explicit known ABI assumption for each class, never an inferred original
    # function prototype. Unknown opcodes/branches must reject the candidate.
    for entry,row in candidates.items():
        for typ,fn in LEAVES:
            try:
                cpp,info=fn(elf,entry)
                candidates[entry]=_evidence(row,typ,cpp,info,output)
                break
            except (ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
                row['attempt_failures'].append({'lifter':typ,'error':str(exc)[:240]})
    # Historical two-register linked caller: previous leaves only.
    phase=output/'_phase1.json'
    phase.write_text(json.dumps({
        'stripped_elf_sha256':scan['input_sha256'],
        'source_read':False,'symbols_used':False,
        'functions':[{'address':row['address'],
                      'status':'CPP_EMITTED_UNVALIDATED' if row['status']!='UNSUPPORTED' else 'UNSUPPORTED',
                      'lifter':row.get('lifter')} for row in candidates.values()]})+'\n')
    try:
        for entry,row in candidates.items():
            if row['status']!='UNSUPPORTED':continue
            try:
                cpp,info=linked_caller(elf,entry,phase)
                candidates[entry]=_evidence(row,'linked_caller',cpp,info,output)
            except (ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
                row['attempt_failures'].append({'lifter':'linked_caller','error':str(exc)[:240]})
    finally:
        phase.unlink(missing_ok=True)
    # Map ABI roles by accepted *lifter category*, not fixed ELF address or
    # original name. Resolve direct BL dependency chain to a fixed point.
    contract={entry:'board_only_mutator' for entry,row in candidates.items()
              if row.get('lifter')=='mutating_leaf'}
    contract.update({entry:'board_column_score_leaf' for entry,row in candidates.items()
                     if row.get('lifter')=='three_arg_memory_leaf'})
    for depth in range(8):
        progress=0
        for entry,row in candidates.items():
            if row['status']!='UNSUPPORTED':continue
            try:
                cpp,info=move_caller(elf,entry,contract)
                candidates[entry]=_evidence(row,'two_arg_board_score_caller',cpp,info,output)
                contract[entry]='board_score_caller'
                progress+=1
            except (ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
                if depth==7:
                    row['attempt_failures'].append({
                        'lifter':'two_arg_board_score_caller','error':str(exc)[:240]})
        if not progress:break
    # Recover a rand-driven stack leaf and its direct caller from stripped
    # executable bytes, not game names or hardcoded entry addresses.
    try:
        rand_leaf,rand_caller,cpp_leaf,cpp_caller,stack_info=generate_stack_pair(elf)
        for entry,code,role,count in (
                (rand_leaf,cpp_leaf,'rand_stack_leaf',stack_info['callee_instructions']),
                (rand_caller,cpp_caller,'rand_stack_caller',stack_info['caller_instructions'])):
            row=candidates.get(entry)
            if row is None or row['status']!='UNSUPPORTED':
                raise ValueError('ambiguous already-handled stack/rand entry')
            candidates[entry]=_evidence(row,role,code,{
                'source_read':False,'symbols_used':False,
                'instructions_translated':count,
                'ABI_assumption':stack_info['ABI_assumption']},output)
    except (ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
        # A different ELF without this exact supported instruction subset
        # must be reported as unsupported rather than approximated.
        for row in candidates.values():
            if row['status']=='UNSUPPORTED':
                row['attempt_failures'].append({'lifter':'rand_stack_pair',
                                                'error':str(exc)[:240]})

    accepted=[row for row in candidates.values() if row['status']!='UNSUPPORTED']
    report={
        'tool':'EdgeAI ARM64 blind multi-stage batch translator',
        'binary_sha256':scan['input_sha256'],
        'source_read':False,'symbols_used':False,
        'input':'stripped ELF; ABI roles from accepted lifter categories',
        'candidate_entry_count':len(candidates),
        'cpp_emitted_candidate_count':len(accepted),
        'unsupported_candidate_count':len(candidates)-len(accepted),
        'instructions_emitted':sum(row['instructions'] for row in accepted),
        'compile_status':'NOT_REQUESTED',
        'behaviorally_validated':False,
        'source_equivalence_proven':False,
        'whole_game_decompiled':False,
        'roles_assigned_by_opcode_compatibility_only':True,
        'ABI_contract_is_assumed':True,
        'functions':list(candidates.values()),
        'limitations':[
            'C++ output and compilation do not establish behavioral equivalence.',
            'ELF stripped source and symbolic metadata not read in generation.',
            'Function names/signatures remain unproved ABI assumptions.',
            'Unknown instructions and callers fail closed.',
            'Full game executable and resource behavior not recovered.'
        ]}
    if compile_cpp and accepted:
        compiler=shutil.which('g++')
        if not compiler:
            report['compile_status']='COMPILER_UNAVAILABLE'
        else:
            args=[compiler,'-std=c++17','-O2','-fPIC','-shared',
                  *[str(output/row['file']) for row in accepted],
                  '-o',str(output/'recovered_candidates.so')]
            job=subprocess.run(args,capture_output=True,text=True,timeout=70)
            report['compile_status']='SUCCEEDED' if job.returncode==0 else 'FAILED'
            if job.returncode:
                report['compiler_stderr']=job.stderr[-2500:]
    (output/'coverage.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--no-compile',action='store_true')
    a=p.parse_args()
    report=run(a.elf,a.output_dir,not a.no_compile)
    print(json.dumps({k:report[k] for k in (
        'candidate_entry_count','cpp_emitted_candidate_count',
        'unsupported_candidate_count','instructions_emitted','compile_status')},indent=2))


if __name__=='__main__':main()
