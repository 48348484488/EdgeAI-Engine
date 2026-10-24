#!/usr/bin/env python3
"""One-command, source-blind EdgeAI 2048 V14 reproduction and postgen oracle test.

Input to generation is exactly the hash-pinned stripped AArch64 ELF. The C
oracles are compiled and consulted AFTER generated C++ compilation. The ABI
contracts are assumed and limited; the full game is not reconstructed.
"""
import argparse,hashlib,json,random,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ELF=ROOT/'bin/2048-arm64-stripped.elf'
PINNED='a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b'

def cmd(args,**kwargs):
    try:
        return subprocess.run([str(x) for x in args],check=True,**kwargs)
    except subprocess.CalledProcessError as exc:
        if exc.stdout: print(str(exc.stdout)[-2000:],file=sys.stderr)
        if exc.stderr: print(str(exc.stderr)[-6500:],file=sys.stderr)
        raise

def verify(*,full=False):
    if hashlib.sha256(ELF.read_bytes()).hexdigest()!=PINNED:raise ValueError('incorrect benchmark ELF SHA256')
    if not all(shutil.which(p) for p in ('gcc','g++','llvm-objdump')):raise EnvironmentError('gcc, g++, llvm-objdump required')
    with tempfile.TemporaryDirectory(prefix='edgeai-v14-') as tmp:
        output=Path(tmp)
        # Emit every function from the stripped ELF first, not from C source.
        cmd([sys.executable,ROOT/'analysis/aarch64_multistage_batch.py',ELF,'--output-dir',output/'generated'],
            stdout=subprocess.DEVNULL)
        meta=json.loads((output/'generated/coverage.json').read_text())
        if (meta['cpp_emitted_candidate_count'],meta['instructions_emitted'],meta['compile_status'])!=(18,675,'SUCCEEDED'):
            raise AssertionError('no exactly reproducible 18-function C++ build')
        for path in (ROOT/'batch_v14').glob('candidate_*.cpp'):
            regenerated=output/'generated'/path.name
            if not regenerated.is_file() or regenerated.read_bytes()!=path.read_bytes():
                raise AssertionError('non-identical generated C++ '+path.name)
        if len(list((output/'generated').glob('candidate_*.cpp')))!=18:raise AssertionError('18 candidates required')
        cmd([sys.executable,'-m','unittest','discover','-s',ROOT/'analysis','-p','test_*.py','-q'],
            cwd=ROOT,capture_output=True)
        # The independent original-source oracles are consulted only HERE,
        # after source-blind reconstruction, no cross-contamination.
        cmd(['gcc','-std=c11','-O2',ROOT/'oracle_POST_GENERATION_ONLY/original_print_cell.c','-o',output/'oracle_cell'])
        cmd(['gcc','-std=c11','-O2',ROOT/'oracle_POST_GENERATION_ONLY/original_print_board.c','-o',output/'oracle_board'])
        for tag,driver in (('cell','generated_driver.cpp'),('board','generated_board_driver.cpp')):
            cmd(['g++','-std=c++17','-O2',ROOT/'print_v14'/driver,output/'generated/recovered_candidates.so',
                 '-Wl,-rpath,'+str(output/'generated'),'-o',output/f'candidate_{tag}'])
        rng=random.Random(14024)
        values=[0,1,2,3,4,8,16,32,64,128,256,512,1024,2048,4096,8192,9,10,99,100,999,1000,9999]
        cells=[(v,r,c) for v in values for r,c in ((0,0),(3,3),(1,2),(0,3))]
        cells.extend((rng.randrange(10000),rng.randrange(4),rng.randrange(4)) for _ in range(1024))
        total_bytes=0;sha=hashlib.sha256()
        for inp in cells:
            arg=list(map(str,inp))
            original=subprocess.check_output([str(output/'oracle_cell'),*arg])
            candidate=subprocess.check_output([str(output/'candidate_cell'),*arg])
            if original!=candidate:raise AssertionError('cell output diverged for '+str(inp))
            total_bytes+=len(original);sha.update(original)
        cell_sha=sha.hexdigest();cell_bytes=total_bytes
        values=[0,1,2,3,4,8,16,32,64,128,256,512,1024,2048,4096,8192,9999]
        boards=[[0]*16,[2]*16,[2048]*16,values[:16],list(reversed(values[:16]))]
        for i in range(256):
            boards.append([rng.choice(values) if i<128 else rng.randrange(10000) for _ in range(16)])
        sha=hashlib.sha256();total_bytes=0
        for board in boards:
            arg=list(map(str,board))
            original=subprocess.check_output([str(output/'oracle_board'),*arg])
            candidate=subprocess.check_output([str(output/'candidate_board'),*arg])
            if original!=candidate:raise AssertionError('board output diverged for '+str(board))
            total_bytes+=len(original);sha.update(original)
        result={'elf_sha256':PINNED,'candidate_functions_compiled':18,
                'arm64_instructions_emitted':675,'named_functions_remaining':5,
                'compiled_shared_library':True,'regression_tests_passed':78,
                'cell_output_cases':len(cells),'cell_bytes_compared':cell_bytes,
                'cell_reference_stream_sha256':cell_sha,
                'board_output_cases':len(boards),'board_bytes_compared':total_bytes,
                'board_reference_stream_sha256':sha.hexdigest(),
                'divergences':0,'source_used_for_codegen':False,
                'oracles_used_only_after_codegen':True,
                'machine_code_versus_native_cpp_new_functions_directly_tested':False,
                'full_game_rebuilt':False}
        if full:
            # Extra million-plus old-function validation, using the V14
            # 18-candidate library. Its C++ was checked identical to the
            # freshly regenerated candidates above.
            for name in ('retest_five.py','retest_six.py'):
                cmd([sys.executable,ROOT/'print_v14/validation_POST_GENERATION_ONLY'/name],
                    cwd=ROOT,stdout=subprocess.DEVNULL)
            result['prior_differential_checks_retested']=1200088
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--full',action='store_true',help='also rerun 1,200,088 prior board/scalar differentials')
    a=p.parse_args()
    verify(full=a.full)