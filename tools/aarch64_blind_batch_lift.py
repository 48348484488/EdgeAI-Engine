#!/usr/bin/env python3
"""Try each stripped ARM64 function entry, produce fail-closed C++ lift coverage.

Every entry discovered directly from the ELF is attempted. Source code and
symbol tables are never read by this program. Accepted ABI is a heuristic
for fixed 16 x uint32_t board pointers and must be validated independently.
"""
import argparse
import json
from pathlib import Path
from aarch64_stripped_discovery import analyze
from aarch64_leaf_lifter import run as lift_reader
from aarch64_mutating_lifter import run as lift_mutator


def run_all(elf, directory):
    scan = analyze(elf)
    directory=Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for x in scan['candidate_entries']:
        entry = int(x['address'], 16)
        attempts = []
        for typ, fn in [('read_only_leaf',lift_reader),('mutating_leaf',lift_mutator)]:
            try:
                cpp, info = fn(elf,entry)
                if not cpp or not info.get('source_read') is False or not info.get('symbols_used') is False:
                    raise ValueError('invalid source-blind provenance')
                file_name = f'candidate_{entry:x}.cpp'
                (directory/file_name).write_text(cpp,encoding='utf-8')
                rows.append({'address':hex(entry), 'status':'CPP_EMITTED_UNVALIDATED',
                    'lifter':typ, 'file':file_name,
                    'instructions':info.get('instructions_translated',info.get('instruction_count')),
                    'ABI_assumption':info.get('known_abi_assumption',info.get('return_abi_assumption'))})
                break
            except (ValueError,RuntimeError,KeyError) as err:
                attempts.append({'lifter':typ,'why':str(err)[:160]})
        else:
            rows.append({'address':hex(entry),'status':'UNSUPPORTED','attempts':attempts})
    accepted=[x for x in rows if x['status']=='CPP_EMITTED_UNVALIDATED']
    return {
        'tool':'EdgeAI blind AArch64 small-game batch lifter',
        'game_input':'ELF stripped; no names or source',
        'source_read':False,'symbols_used':False,'behaviorally_validated':False,
        'stripped_elf_sha256':scan['input_sha256'],
        'entry_candidates':len(rows),
        'cpp_emitted_function_candidates':len(accepted),
        'unsupported_entry_candidates':len(rows)-len(accepted),
        'instructions_emitted':sum(x['instructions'] for x in accepted),
        'accepted_signature_is_hypothesis':True,
        'whole_game_recovered':False,
        'functions':rows,
        'limitations':['Emitted functions not yet validated by oracle or in-game execution.',
                       'Some candidates can be false entrypoints or have incompatible ABI.',
                       'Function coverage requires independent post-generation oracle comparison.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path)
    p.add_argument('--output-dir',type=Path,required=True)
    a=p.parse_args()
    report=run_all(a.elf,a.output_dir)
    (a.output_dir/'coverage.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('entry_candidates','cpp_emitted_function_candidates',
                        'unsupported_entry_candidates','instructions_emitted')},indent=2))


if __name__=='__main__':main()
