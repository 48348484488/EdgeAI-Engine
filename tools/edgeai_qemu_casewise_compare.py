#!/usr/bin/env python3
"""Original ELF QEMU -> native C++ individual call comparison, source-blind.

See results/2048_real_arm64_22000_casewise_2026-10-17.json.
Hashes are FNV64, so equality is strong sampled evidence, not a proof.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re

MASK32=(1<<32)-1
MASK64=(1<<64)-1
PRIME=1099511628211
BASIS=14695981039346656037
SEED=0x31415926
SPECIAL=(0,1,2,4,8,16,32,64,128,256,512,1024,2048,0xffffffff,0x80000000,65535,10,100,1000,10000,4096,8192)
CASE_RE=re.compile(r'^ARM64_CASE slot=(\d+) case=(\d+) fnv64=([0-9a-f]{16})$')
SUMMARY_RE=re.compile(r'^ARM64_REAL_ELF slot=(\d+) addr=0x([0-9a-f]{16}) role=(\d+) calls=(\d+) fnv64=([0-9a-f]{16})$')


def next_rand(x):
    x^=(x<<13)&MASK32
    x^=x>>17
    x^=(x<<5)&MASK32
    return x&MASK32


def put32(h,v):
    for shift in (0,8,16,24):
        h=((h^((v>>shift)&255))*PRIME)&MASK64
    return h


def mkboard(seed,i):
    arr=[]
    for j in range(16):
        seed=next_rand(seed)
        if i==0:v=0
        elif i==1:v=2
        elif i==2:v=2048
        elif i==3:v=j
        elif i==4:v=MASK32
        elif i==5:v=0 if j%2 else 2048
        elif i==6:v=j*16
        else:v=(0,2,4,8,2048,MASK32,seed,seed&255)[seed&7]
        arr.append(v)
    return seed,arr


def check_cases(records,manifest,rounds):
    lines=Path(records).read_text().splitlines()
    entries=manifest['entries']
    if len(lines)!=len(entries)*(rounds+1):
        raise ValueError('Machine case count differs from manifest and rounds')
    expected=[];ix=0
    for slot,e in enumerate(entries):
        block=[]
        for case in range(rounds):
            m=CASE_RE.fullmatch(lines[ix])
            if not m or int(m[1])!=slot or int(m[2])!=case:
                raise ValueError(f'Machine case order or structure corrupted at line {ix}')
            block.append(m[3]);ix+=1
        m=SUMMARY_RE.fullmatch(lines[ix]);ix+=1
        if (not m or int(m[1])!=slot or int(m[2],16)!=int(e['address'],16)
            or int(m[3])!=manifest['roles'][e['role']] or int(m[4])!=rounds
            or m[5]!=block[-1]):
            raise ValueError('Machine block summary disagrees with case digests')
        expected.append(block)
    return expected


def verify(machine_cases,elf,manifest_path,library,rounds=2000):
    config=json.loads(Path(manifest_path).read_text())
    sha=hashlib.sha256(Path(elf).read_bytes()).hexdigest()
    if sha!=config['elf_sha256']:
        raise ValueError('Wrong original ELF SHA; comparison would be invalid')
    cases=check_cases(machine_cases,config,rounds)
    lib=ctypes.CDLL(str(Path(library).resolve()))
    outcome=[]
    for slot,e in enumerate(config['entries']):
        addr=int(e['address'],16);role=e['role']
        fn=getattr(lib,f'recovered_{addr:x}')
        if role=='scalar_leaf':
            fn.argtypes=[ctypes.c_uint32]
            fn.restype=ctypes.c_uint32
        elif role=='mutating_leaf':
            fn.argtypes=[ctypes.POINTER(ctypes.c_uint32)]
            fn.restype=None
        elif role=='read_only_leaf':
            fn.argtypes=[ctypes.POINTER(ctypes.c_uint32)]
            fn.restype=ctypes.c_uint32
        elif role=='board_score_caller':
            fn.argtypes=[ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_uint32)]
            fn.restype=ctypes.c_uint32
        elif role=='board_column_score_leaf':
            fn.argtypes=[ctypes.POINTER(ctypes.c_uint32),ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
            fn.restype=ctypes.c_uint32
        else:
            raise ValueError('Unknown ABI role: '+repr(role))
        h=BASIS;seed=SEED;first=None
        for i in range(rounds):
            h=put32(h,i)
            repro={'entry':e['address'],'role':role,'index':i}
            if role=='scalar_leaf':
                if i<len(SPECIAL):value=SPECIAL[i]
                else:seed=next_rand(seed);value=seed
                h=put32(h,value)
                ret=fn(value)
                h=put32(h,int(ret))
                repro.update(argument=value,return_value=int(ret))
            else:
                seed,board=mkboard(seed,i)
                for v in board:h=put32(h,v)
                cboard=(ctypes.c_uint32*16)(*board)
                repro['board_input']=board
                if role=='mutating_leaf':
                    fn(cboard)
                elif role=='read_only_leaf':
                    ret=fn(cboard);h=put32(h,int(ret));repro['return_value']=int(ret)
                else:
                    score_before=(i*73+11)&MASK32
                    score=ctypes.c_uint32(score_before)
                    h=put32(h,score_before)
                    repro['score_input']=score_before
                    if role=='board_column_score_leaf':
                        column=i&3
                        h=put32(h,column)
                        repro['column']=column
                        ret=fn(cboard,column,ctypes.byref(score))
                    else:ret=fn(cboard,ctypes.byref(score))
                    h=put32(h,int(ret))
                    h=put32(h,int(score.value))
                    repro.update(return_value=int(ret),score_output=int(score.value))
                out=list(map(int,cboard))
                repro['board_output']=out
                for v in out:h=put32(h,v)
            native=f'{h:016x}'
            if native!=cases[slot][i] and first is None:
                first={'case':i,'original_machine_prefix':cases[slot][i],
                       'reconstructed_cpp_prefix':native,'candidate_state':repro}
        outcome.append({'address':e['address'],'role':role,'cases':rounds,
                        'all_case_prefixes_identical':first is None,
                        'machine_final_digest':cases[slot][-1],
                        'cpp_final_digest':f'{h:016x}',
                        'first_mismatch':first})
    matches=sum(item['all_case_prefixes_identical'] for item in outcome)
    return {'test':'Case-by-case original AArch64 machine ELF vs native generated EdgeAI C++',
            'original_elf_sha256':sha,
            'machine_raw_sha256':hashlib.sha256(Path(machine_cases).read_bytes()).hexdigest(),
            'source_read':False,'symbols_used':False,
            'original_cpu':'QEMU AArch64 user mode',
            'reconstructed_cpu':'host x86_64 generated C++',
            'function_count':len(outcome),
            'cases_compared':len(outcome)*rounds,
            'functions_identical_on_sample':matches,
            'functions_with_mismatches':len(outcome)-matches,
            'passed':len(outcome)==matches,
            'methods':{'comparison':'rolling FNV64 after each individual function call','rounds':rounds},
            'results':outcome,
            'limitations':['FNV64 hashes are probabilistic fingerprints, not collision-free equality proofs.',
             'Per-call mismatch points to exact input but original machine state is only available through its hash.',
             'Only supported ABI-contract candidates are tested; no complete game equivalence claimed.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('machine-cases','elf','manifest','library','report'):
        p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    result=verify(a.machine_cases,a.elf,a.manifest,a.library)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:result[k] for k in ('function_count','cases_compared','functions_identical_on_sample','functions_with_mismatches','passed')},indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
