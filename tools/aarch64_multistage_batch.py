#!/usr/bin/env python3
"""Source-blind ARM64 C++ reconstruction: multi-pass leaf and caller discovery.

Processes every function-entry candidate found in the stripped ELF. Separates
'CPP generated' from 'compiler succeeded' and 'behavior validated'. Maps callee
roles by the accepted lifter's ABI contract, never by source, names or hardcoded
ELF address. Conservatively rejects unknown frame or BL target behavior.
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
from aarch64_branch_printf_lifter import lift as branch_printf_leaf
from aarch64_print_loop_caller_lifter import lift as print_loop_caller
from aarch64_stateful_printf_lifter import lift as stateful_printf_leaf

LEAVES=(('read_only_leaf',read_leaf),('mutating_leaf',mutable_leaf),
        ('scalar_leaf',scalar_leaf),('three_arg_memory_leaf',multimem_leaf),
        ('terminal_printf_leaf',printf_leaf),
        ('terminal_static_sequence',static_printf_sequence))


def _evidence(row,typ,src,meta,output):
    if meta.get('symbols_used') is not False or meta.get('source_read') is not False:
        raise ValueError('candidate lift used source or ELF symbols')
    (output / f'candidate_{int(row["address"],16):x}.cpp').write_text(src,encoding='utf-8')
    return {'address':row['address'],'status':'CPP_EMITTED_NOT_BEHAVIORALLY_VALIDATED',
            'lifter':typ,'file':f'candidate_{int(row["address"],16):x}.cpp',
            'instructions':meta.get('instructions_translated',meta.get('instruction_count')),
            'abi_assumption':meta.get('ABI_assumption',meta.get('assumed_abi',
                                meta.get('known_abi_assumption',meta.get('return_abi_assumption')))),
            'attempt_failures':row.get('attempt_failures',[])}


def _compile_candidates(output, selected):
    """Link atomically, rejecting unresolved generated symbols (not just syntax)."""
    library = output/'recovered_candidates.so'
    temporary = output/'recovered_candidates.so.tmp'
    library.unlink(missing_ok=True)
    temporary.unlink(missing_ok=True)
    compiler = shutil.which('g++')
    if not compiler:
        return 'COMPILER_UNAVAILABLE', None
    args = [compiler, '-std=c++17', '-O2', '-fPIC', '-shared',
            '-Wl,-z,defs',
            *[str(output/row['file']) for row in selected],
            '-o', str(temporary)]
    try:
        process = subprocess.run(args, capture_output=True, text=True, timeout=70)
        if process.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
            return 'FAILED', (process.stderr or 'linker produced no shared library')[-2500:]
        temporary.replace(library)
        return 'SUCCEEDED', None
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 'FAILED', str(exc)[-2500:]
    finally:
        temporary.unlink(missing_ok=True)


def run(elf,output,compile_cpp=True,enable_stateful_printf=False):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    # A re-run must not leave prior candidates or a prior successful library
    # that could be misinterpreted as products of the current input.
    for stale in output.glob('candidate_*.cpp'):
        stale.unlink()
    for name in ('recovered_candidates.so', 'recovered_candidates.so.tmp', 'coverage.json'):
        (output/name).unlink(missing_ok=True)
    scan=analyze(elf)
    if scan.get('symbols_used') is not False or scan.get('source_read') is not False:
        raise ValueError('stripped scan provenance missing')
    candidates={int(item['address'],16):{'address':item['address'],'status':'UNSUPPORTED',
                                   'attempt_failures':[]} for item in scan['candidate_entries']}
    # The three-argument ABI is declared, not inferred. Strict instruction
    # coverage prevents accidentally treating arbitrary functions as matches.
    for entry,row in candidates.items():
        for typ,fn in LEAVES:
            try:
                source,info=fn(elf,entry)
                candidates[entry]=_evidence(row,typ,source,info,output)
                break
            except (ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
                row['attempt_failures'].append({'lifter':typ,'error':str(exc)[:240]})

    # The historical two-register linked caller algorithm works only with
    # read-only and mutating leaves; its own provenance checks are retained.
    phase=output/'_phase1.json'
    phase.write_text(json.dumps({'stripped_elf_sha256':scan['input_sha256'],
                                 'source_read':False,'symbols_used':False,
                                 'functions':[{'address':row['address'],
                                   'status': 'CPP_EMITTED_UNVALIDATED' if row['status']!='UNSUPPORTED' else 'UNSUPPORTED',
                                   'lifter':row.get('lifter')} for row in candidates.values()]})+'\n')
    try:
        for entry,row in candidates.items():
            if row['status']!='UNSUPPORTED':continue
            try:
                source,info=linked_caller(elf,entry,phase)
                candidates[entry]=_evidence(row,'linked_caller',source,info,output)
            except (ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
                row['attempt_failures'].append({'lifter':'linked_caller','error':str(exc)[:240]})
    finally:
        phase.unlink(missing_ok=True)

    # Build an ABI-role map FROM THE LIFTER TYPES, not function names or a
    # static game-address list. Iterate through the call graph until fixed
    # point (max 8 levels). Reject calls whose ABI is not yet reconstructed.
    contract={entry:'board_only_mutator' for entry,row in candidates.items() if row.get('lifter')=='mutating_leaf'}
    contract.update({entry:'board_column_score_leaf' for entry,row in candidates.items() if row.get('lifter')=='three_arg_memory_leaf'})
    for depth in range(8):
        progress=0
        for entry,row in candidates.items():
            if row['status']!='UNSUPPORTED':continue
            try:
                source,info=move_caller(elf,entry,contract)
                candidates[entry]=_evidence(row,'two_arg_board_score_caller',source,info,output)
                contract[entry]='board_score_caller'
                progress+=1
            except (ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
                # Log only terminal diagnostic per call depth; the next pass
                # may gain new dependencies from a previously accepted callee.
                if depth==7:
                    row['attempt_failures'].append({'lifter':'two_arg_board_score_caller','error':str(exc)[:240]})
        if progress==0:break
    # Decode paired stack/rand leaf and its direct caller from the stripped
    # ELF itself. No hardcoded entrypoints, source or function-name mapping.
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
        # Unsupported builds legitimately lack this pattern; do not fabricate
        # output or mark any function recovered.
        for row in candidates.values():
            if row['status']=='UNSUPPORTED':
                row['attempt_failures'].append({'lifter':'rand_stack_pair',
                                                'error':str(exc)[:240]})

    # Source-blind branch-and-printf leaf, then its memory-loop caller.
    # Uses previously accepted scalar ABI roles; never a fixed game address.
    entries=sorted(candidates)
    limits={e:(entries[i+1] if i+1<len(entries)
                else int(scan['text_address'],16)+scan['text_size_bytes'])
            for i,e in enumerate(entries)}
    scalar_entries={e for e,row in candidates.items() if row.get('lifter')=='scalar_leaf'}
    if scalar_entries:
        for entry,row in candidates.items():
            if row['status']!='UNSUPPORTED':continue
            try:
                code,meta=branch_printf_leaf(elf,entry,limits[entry],scalar_entries)
                candidates[entry]=_evidence(row,'branch_printf_linked_scalar',code,meta,output)
            except (ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
                row['attempt_failures'].append({'lifter':'branch_printf_linked_scalar','error':str(exc)[:240]})
    printer_entries={e for e,row in candidates.items()
                     if row.get('lifter')=='branch_printf_linked_scalar'}
    if printer_entries:
        for entry,row in candidates.items():
            if row['status']!='UNSUPPORTED':continue
            try:
                code,meta=print_loop_caller(elf,entry,limits[entry],printer_entries)
                candidates[entry]=_evidence(row,'read_only_print_loop_caller',code,meta,output)
            except (ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
                row['attempt_failures'].append({'lifter':'read_only_print_loop_caller','error':str(exc)[:240]})

    # V15 opt-in: bounded .bss-u32 printer. A generated C++ file is NOT
    # evidence of behavioral validation; external QEMU parity is separate.
    if enable_stateful_printf:
        for entry,row in candidates.items():
            if row['status']!='UNSUPPORTED':continue
            try:
                code,meta=stateful_printf_leaf(elf,entry,limits[entry])
                candidates[entry]=_evidence(row,'stateful_printf_u32',code,meta,output)
            except (ValueError,KeyError,RuntimeError,subprocess.CalledProcessError) as exc:
                row['attempt_failures'].append({'lifter':'stateful_printf_u32','error':str(exc)[:240]})

    selected=[row for row in candidates.values() if row['status']!='UNSUPPORTED']
    report={'tool':'EdgeAI ARM64 blind multi-stage batch translator',
            'binary_sha256':scan['input_sha256'],'source_read':False,'symbols_used':False,
            'input':'ELF stripped; ABI roles from source-blind lifter modules',
            'candidate_entry_count':len(candidates),
            'cpp_emitted_candidate_count':len(selected),
            'unsupported_candidate_count':len(candidates)-len(selected),
            'instructions_emitted':sum(row['instructions'] for row in selected),
            'compile_status':'NOT_REQUESTED','behaviorally_validated':False,
            'source_equivalence_proven':False,'whole_game_decompiled':False,
            'roles_inferred_from_opcode_compatibility_only':True,
            'known_abi_contract_is_assumed':True,
            'functions':list(candidates.values())}
    if enable_stateful_printf:
        report['experimental_stateful_printf_enabled']=True
    if compile_cpp and selected:
        report['compile_status'], error = _compile_candidates(output, selected)
        if error:
            report['compiler_stderr'] = error
    (output/'coverage.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--no-compile',action='store_true')
    p.add_argument('--enable-stateful-printf',action='store_true',
                   help='opt into bounded V15 global-u32 printf reconstruction')
    a=p.parse_args()
    rep=run(a.elf,a.output_dir,not a.no_compile,a.enable_stateful_printf)
    print(json.dumps({k:rep[k] for k in ('candidate_entry_count','cpp_emitted_candidate_count',
        'unsupported_candidate_count','instructions_emitted','compile_status')},indent=2))

if __name__=='__main__':main()