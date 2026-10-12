#!/usr/bin/env python3
"""Build real static ARM32 Linux winner tests with Clang; optionally run QEMU.

Unlike the GCC-based QEMU test, this harness needs no ARM sysroot, libc or GCC.
If QEMU is absent the report records 'not_executed', never a passing run.
"""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from recover_winner import emit_cpp
from recover_winner_variants import recover_variants
from validate_winner_reconstruction import ROOT, SOURCE

HARNESS=ROOT/'tests/winner_freestanding_arm.cpp'
TARGET='--target=armv7-linux-gnueabihf'
MODES=('1','2','3','s','z')


def invoke(command,timeout=120):
    try:
        return subprocess.run(command,check=True,capture_output=True,text=True,timeout=timeout).stdout
    except subprocess.CalledProcessError as error:
        raise RuntimeError('Command failed: '+' '.join(map(str,command))+'\n'+error.stderr[-3000:]) from error


def verify_static_arm_elf(path):
    data=Path(path).read_bytes()
    if len(data)<52 or data[:6]!=b'\x7fELF\x01\x01':
        raise ValueError('not little-endian ELF32')
    e_type,e_machine=struct.unpack_from('<HH',data,16)
    if (e_type,e_machine)!=(2,40):
        raise ValueError('not an executable ARM ELF')
    phoff=struct.unpack_from('<I',data,28)[0]
    phsize,phnum=struct.unpack_from('<HH',data,42)
    if phsize<32 or phnum==0 or phoff+phnum*phsize>len(data):
        raise ValueError('invalid ELF program headers')
    types=[struct.unpack_from('<I',data,phoff+i*phsize)[0] for i in range(phnum)]
    if 3 in types:
        raise ValueError('unexpected dynamic program interpreter')
    if 1 not in types:
        raise ValueError('missing PT_LOAD')
    return {'elf_class':'ELF32','machine':'ARM','type':'ET_EXEC','dynamic_interpreter':False,
            'entry':hex(struct.unpack_from('<I',data,24)[0]),'size_bytes':len(data)}


def validate(output=ROOT/'results/winner_freestanding_arm32.json',
             qemu=shutil.which('qemu-arm'),require_qemu=False,optimizations=MODES):
    report={'architecture':'ARM32 Linux EABI','compiler':'Clang + LLD',
            'libc_required':False,'gcc_arm_required':False,
            'emulator':'qemu-arm' if qemu else None,
            'execution_status':'pending','runs':[]}
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        original_o=td/'original.o'
        harness_o=td/'harness.o'
        invoke(['clang',TARGET,'-marm','-O1','-ffreestanding','-fno-builtin',
                '-fno-inline','-nostdlib','-Dwinner=original_winner',
                '-Dplay=original_play','-Dstart=original_start','-c',str(SOURCE),'-o',str(original_o)])
        invoke(['clang++',TARGET,'-marm','-O1','-ffreestanding','-fno-exceptions',
                '-fno-rtti','-fno-builtin','-c',str(HARNESS),'-o',str(harness_o)])
        for opt in optimizations:
            if opt not in MODES:raise ValueError('unsupported optimization')
            compiled=td/('clang_'+opt+'.elf')
            stripped=td/('stripped_'+opt+'.elf')
            cpp=td/('recovered_'+opt+'.cpp')
            candidate=td/('candidate_'+opt+'.o')
            runner=td/('runner_'+opt+'.elf')
            invoke(['clang','--target=armv7-none-eabi','-marm','-O'+opt,
                    '-fno-inline','-nostdlib','-fuse-ld=lld',
                    '-Wl,-Ttext=0x1000','-Wl,-e,start',str(SOURCE),'-o',str(compiled)])
            invoke(['llvm-objcopy','--strip-all',str(compiled),str(stripped)])
            recovered=recover_variants(stripped)
            cpp.write_text(emit_cpp(recovered),encoding='utf-8')
            invoke(['clang++',TARGET,'-marm','-O1','-ffreestanding',
                    '-fno-exceptions','-fno-rtti','-fno-builtin',
                    '-c',str(cpp),'-o',str(candidate)])
            invoke(['clang++',TARGET,'-marm','-O1','-ffreestanding',
                    '-fno-exceptions','-fno-rtti','-nostdlib','-fuse-ld=lld',
                    '-static','-Wl,-e,_start',str(original_o),str(candidate),
                    str(harness_o),'-o',str(runner)])
            elf=verify_static_arm_elf(runner)
            entry={'optimization':'-O'+opt,'recognized_pattern':recovered['optimization_pattern'],
                   'elf':elf,'execution_status':'not_executed','behavior':None}
            if qemu:
                behavior=json.loads(invoke([qemu,str(runner)],timeout=180))
                entry['behavior']=behavior
                entry['execution_status']='passed' if behavior=={
                    'tested_cases':85223,'mismatches':0,'passed':True} else 'failed'
            report['runs'].append(entry)
            if entry['execution_status']=='failed':break
    successes=[x for x in report['runs'] if x['execution_status']=='passed']
    report['execution_status']=('passed' if len(successes)==len(optimizations) else
        'not_executed_missing_qemu' if not qemu else 'failed_or_incomplete')
    report['qemu_tested_cases']=sum(x['behavior']['tested_cases'] for x in successes)
    report['qemu_mismatches']=sum(x['behavior']['mismatches'] for x in successes)
    report['compiled_runners']=len(report['runs'])
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'compiled_runners':report['compiled_runners'],
                      'execution_status':report['execution_status'],
                      'qemu_tested_cases':report['qemu_tested_cases'],
                      'report':str(output)}))
    if require_qemu and report['execution_status']!='passed':
        raise RuntimeError('QEMU ARM test not passed; see saved report')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/winner_freestanding_arm32.json')
    parser.add_argument('--require-qemu',action='store_true')
    parser.add_argument('--qemu',type=str,default=shutil.which('qemu-arm'))
    parser.add_argument('--optimizations',type=str,default=','.join(MODES))
    args=parser.parse_args()
    try:
        validate(args.output,args.qemu,args.require_qemu,args.optimizations.split(','))
    except (ValueError,RuntimeError) as exc:
        parser.exit(2,'ARM32 validation: '+str(exc)+'\n')
