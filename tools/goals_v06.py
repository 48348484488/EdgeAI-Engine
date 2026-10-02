"""Independent-data research stages used by the common local goal executor."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def stage_commands(profile,build,threads):
    if profile not in ('independent','independent-quick') or not 1<=threads<=64:raise ValueError('invalid independent profile/threads')
    quick=profile.endswith('-quick');py=sys.executable;build=Path(build).resolve();result=ROOT/('results/v06/quick' if quick else 'results/v06');modeldir=ROOT/('models/quick_v06' if quick else 'models/external_v06');report=result/'training.json'
    train=[py,str(ROOT/'benchmarks/tokenization_v06.py'),'--cpu-seconds','1' if quick else '20','--seeds']+(['11'] if quick else ['11','22','33'])+['--threads',str(threads),'--build',str(build),'--out',str(report),'--model-dir',str(modeldir),'--resume']
    return [
        ('configure',['cmake','-S',str(ROOT),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release']),
        ('build',['cmake','--build',str(build),'--config','Release','-j','2']),
        ('cpp_tests',['ctest','--test-dir',str(build),'-C','Release','--output-on-failure']),
        ('python_tests',[py,'-m','unittest','discover','-s',str(ROOT/'tests'),'-p','test_*.py','-v']),
        ('snapshot_integrity',[py,str(ROOT/'tools/external_data.py')]),
        ('train_only_tokenizer',[py,str(ROOT/'tools/prepare_v06.py')]),
        ('bpe_parity',[py,str(ROOT/'tools/verify_bpe.py'),'--build',str(build),'--out',str(result/'parity.json')]),
        ('equal_cpu_external_training',train),
        ('native_external',[py,str(ROOT/'benchmarks/native_v06.py'),'--build',str(build),'--report',str(report),'--out',str(result/'native.json'),'--repeats','1' if quick else '5']),
        ('capability_tasks',[py,str(ROOT/'benchmarks/capability_v06.py'),'--build',str(build),'--report',str(report),'--out',str(result/'capability.json')]),
        ('energy_probe',[py,str(ROOT/'benchmarks/measure_energy.py'),'--out',str(result/'energy.json'),'--',str(build/'edgeai_text_eval'),str(modeldir/'bpe513-seed11.edge'),str(ROOT/'data/cpython_snapshot/test.rawblocks')]),
        ('validate_reports',[py,str(ROOT/'tools/validate_v06.py'),'--directory',str(result)]),
    ]
