"""Short offline verified-search cycle. No downloads or training."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def stage_commands(profile,build,threads):
    if profile!='indexed' or not 1<=threads<=256:raise ValueError('invalid profile/threads')
    build=Path(build).resolve();py=sys.executable;out=ROOT/'results/v010'
    return [
      ('configure',['cmake','-S',str(ROOT),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release']),
      ('build',['cmake','--build',str(build),'--config','Release','-j','2']),
      ('cpp_tests',['ctest','--test-dir',str(build),'--output-on-failure']),
      ('python_tests',[py,'-m','unittest','discover','-s',str(ROOT/'tests'),'-p','test_*.py','-v']),
      ('original_lookup',[py,str(ROOT/'benchmarks/code_lookup_v09.py'),'--build',str(build),'--out',str(out/'original_retrieval.json')]),
      ('verified_session',[py,str(ROOT/'benchmarks/code_session_v010.py'),'--build',str(build),'--out',str(out/'code_session.json')]),
      ('model_parity',[py,str(ROOT/'tools/verify_instructions.py'),'--build',str(build),'--out',str(out/'parity.json')]),
      ('energy_probe',[py,str(ROOT/'benchmarks/measure_energy.py'),'--out',str(out/'energy.json'),'--',str(build/'edgeai_code_search'),str(ROOT),'greedy_token','--json']),
      ('package_smoke',[py,str(ROOT/'tools/package_smoke.py')])]
