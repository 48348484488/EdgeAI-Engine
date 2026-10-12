#!/usr/bin/env python3
"""Run native differential validation of stripped winner across Clang options."""
import argparse
import hashlib
import json
from pathlib import Path
from validate_winner_reconstruction import ROOT, SOURCE, validate

OPTIMIZATIONS=('1','2','3','s','z')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/winner_variants_validation.json')
    args=parser.parse_args()
    base=args.output.parent
    cases=[]
    for opt in OPTIMIZATIONS:
        report=validate(output=base/f'winner_variant_{opt}.json',
                        candidate_output=base/f'winner_variant_{opt}.cpp',
                        strip_symbols=True,optimization=opt)
        behavior=report['native_differential']
        cases.append({'optimization':'-O'+opt,
                      'fingerprint':report['extraction']['optimization_pattern'],
                      'triplets':report['extraction']['triplets'],
                      'symbols_removed':report['stripped_elf_tested'],
                      'arm32_candidate_compiled':report['arm_candidate_compiled'],
                      'tested_cases':behavior['tested_cases'],
                      'mismatches':behavior['mismatches']})
    total=sum(x['tested_cases'] for x in cases)
    mismatches=sum(x['mismatches'] for x in cases)
    aggregate={'reference':'Clang ARM32 little-endian ELF stripped with llvm-objcopy --strip-all',
               'test_fixture_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
               'test_scope':'Five clang optimization levels for known winner fixture',
               'optimizations':cases,'total_native_comparisons':total,
               'mismatches':mismatches,
               'all_arm32_candidates_compiled':all(x['arm32_candidate_compiled'] for x in cases),
               'qemu_tested':False,'different_compilers_tested':False,
               'generic_decompilation':False}
    if total!=5*327684 or mismatches or not aggregate['all_arm32_candidates_compiled']:
        raise AssertionError('winner variants validation failed')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(aggregate,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'optimizations':len(cases),'comparisons':total,'mismatches':mismatches}))
    return aggregate

if __name__=='__main__':
    main()
