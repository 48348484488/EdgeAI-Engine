"""Sequential CPU-only instruction milestones, no installs/network/confirmation."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def stage_commands(profile,build,threads):
    if profile not in ('instructions','instructions-quick') or not 1<=threads<=64:raise ValueError('invalid instruction profile/threads')
    py=sys.executable;build=Path(build).resolve();quick=profile.endswith('-quick')
    result=ROOT/('results/v07/quick' if quick else 'results/v07');models=ROOT/('models/quick_v07' if quick else 'models/instructions_v07');report=result/'training.json'
    train=[py,str(ROOT/'benchmarks/instruction_v07.py'),'--cpu-seconds','2' if quick else '60','--seeds']+(['11'] if quick else ['11','22','33'])+['--threads',str(threads),'--out',str(report),'--model-dir',str(models),'--resume']
    return [
        ('configure',['cmake','-S',str(ROOT),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release']),
        ('build',['cmake','--build',str(build),'--config','Release','-j','2']),
        ('cpp_tests',['ctest','--test-dir',str(build),'-C','Release','--output-on-failure']),
        ('python_tests',[py,'-m','unittest','discover','-s',str(ROOT/'tests'),'-p','test_*.py','-v']),
        ('frozen_synthetic_data',[py,str(ROOT/'tools/validate_instructions.py'),'--data-only']),
        ('legacy_bpe_parity',[py,str(ROOT/'tools/verify_bpe.py'),'--build',str(build),'--out',str(result/'legacy_parity.json')]),
        ('response_only_training',train),
        ('unassisted_native_evaluation',[py,str(ROOT/'benchmarks/instruction_eval_v07.py'),'--build',str(build),'--report',str(report),'--out',str(result/'evaluation.json')]),
        ('legacy_transfer_diagnostic',[py,str(ROOT/'benchmarks/instruction_legacy_v07.py'),'--build',str(build),'--report',str(report),'--out',str(result/'legacy_diagnostic.json')]),
        ('trained_eos_parity',[py,str(ROOT/'tools/verify_instructions.py'),'--build',str(build),'--report',str(report),'--out',str(result/'parity.json')]),
        ('energy_probe',[py,str(ROOT/'benchmarks/measure_energy.py'),'--out',str(result/'energy.json'),'--',str(build/'edgeai_generate'),str(models/'seed11-after.edge'),str(ROOT/'data/instructions_v07/energy_prompt.txt'),str(result/'energy_output.bin'),'32']),
        ('validate_evidence',[py,str(ROOT/'tools/validate_instructions.py'),'--directory',str(result)]),
    ]
