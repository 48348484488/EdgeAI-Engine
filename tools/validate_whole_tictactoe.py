#!/usr/bin/env python3
"""End-to-end whole tiny-game reconstruction check, with explicit source-assist caveat.

winner(): read-only ARM32 ELF pattern recovery.
play(): existing ARM evidence -> template, but its rules helper ALSO READS C source.
start(): read-only ARM32 ELF call-sequence recovery.
All three candidates are compiled, linked together and compared against the
independent original C game's return + final board over 278528 starting boards.
This is not general-purpose, autonomous or byte-identical decompilation.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'examples/reverse/tictactoe.c'
HARNESS=ROOT/'tests/whole_game_differential_harness.cpp'


def invoke(argv):
    return subprocess.run([str(x) for x in argv], check=True, capture_output=True, text=True, timeout=180).stdout


def validate(output=ROOT/'results/whole_game_rebuild.json'):
    with tempfile.TemporaryDirectory() as folder:
        temp=Path(folder)
        elf=temp/'game-arm32.elf'
        invoke(['clang','--target=armv7-none-eabi','-marm','-O1','-fno-inline',
                '-nostdlib','-fuse-ld=lld','-Wl,-Ttext=0x1000','-Wl,-e=start',
                SOURCE,'-o',elf])
        winner=temp/'winner.cpp'
        play=temp/'play.cpp'
        start=temp/'start.cpp'
        win_report=temp/'winner.json'
        play_report=temp/'play.json'
        start_report=temp/'start.json'
        invoke([sys.executable,ROOT/'tools/recover_winner.py',elf,
                '--cpp',winner,'--report',win_report])
        invoke([sys.executable,ROOT/'tools/generate_play_candidate.py',
                '--output',play,'--report',play_report])
        invoke([sys.executable,ROOT/'tools/recover_start_arm.py',elf,
                '--cpp',start,'--report',start_report])
        start_evidence=json.loads(start_report.read_text())
        win_evidence=json.loads(win_report.read_text())
        play_evidence=json.loads(play_report.read_text())
        if len(start_evidence['moves'])!=5 or len(win_evidence['triplets'])!=8:
            raise ValueError('game function fingerprint does not match tested boundary')
        if not play_evidence.get('not_inferred_from_binary'):
            raise ValueError('source/template assumptions must be recorded')
        objs=[]
        for stem,cpp in (('winner',winner),('play',play),('start',start)):
            arm=temp/(stem+'_arm.o')
            invoke(['clang++','--target=armv7-none-eabi','-marm','-O1',
                    '-ffreestanding','-fno-exceptions','-fno-rtti',
                    '-c',cpp,'-o',arm])
            if not arm.is_file() or arm.stat().st_size<100:
                raise ValueError('candidate did not compile for ARM')
            native=temp/(stem+'_native.o')
            invoke(['clang++','-std=c++17','-O1','-c',cpp,'-o',native])
            objs.append(native)
        original=temp/'original.o'
        invoke(['clang','-std=c11','-O1','-Dwinner=original_winner',
                '-Dplay=original_play','-Dstart=original_start','-c',
                SOURCE,'-o',original])
        executable=temp/'whole-game-differential'
        invoke(['clang++','-std=c++17','-O1',HARNESS,original,*objs,'-o',executable])
        result=json.loads(invoke([executable]))
        if not result.get('passed') or result['tested_cases']!=278528 or result['mismatches']:
            raise AssertionError('whole game behavioral mismatch')
        report={
            'status':'WHOLE_SMALL_GAME_BEHAVIORAL_TEST_PASS',
            'fixture':'tic-tac-toe, single C source, three compiled ARM32 functions',
            'function_count':3,
            'compiled_arm32_candidates':['winner','play','start'],
            'binary_only_recovered_functions':['winner','start'],
            'source_assisted_functions':['play'],
            'original_C_source_used_only_for_reference':False,
            'original_C_source_used_for_play_rules':True,
            'whole_game_autonomous_decompilation':False,
            'source_code_identical':False,
            'native_differential':result,
            'start_moves_extracted_from_arm32':start_evidence['moves'],
            'winner_table_triplets_extracted_from_arm32':len(win_evidence['triplets']),
            'limitations':[
                'Only one known Clang ARM32 -O1 game fingerprint tested.',
                'play() rule inference reads the original example C: still a source-assisted reconstruction.',
                'The named function signatures and calling semantics are supplied templates.',
                '278528 input states test behavior; they do not prove every execution path or byte identity.',
                'ARM32 candidate objects compiled; native host differential executed (not qemu-arm).',
                'Not tested on an Android game, large Unity game, or stripped executable.'
            ]
        }
        output=Path(output)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2)+'\n')
        return report


if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('--output',type=Path,default=ROOT/'results/whole_game_rebuild.json')
    args=a.parse_args()
    report=validate(args.output)
    print(json.dumps(report,indent=2))
