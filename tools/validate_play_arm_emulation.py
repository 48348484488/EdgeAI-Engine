#!/usr/bin/env python3
"""Compare original and generated play() as ARM Linux binaries under qemu-arm."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def execute(argv):
    return subprocess.run(argv,cwd=ROOT,check=True,capture_output=True,text=True).stdout

def run(output=Path("results/play_arm_emulation.json")):
    with tempfile.TemporaryDirectory() as tmp:
        d=Path(tmp)
        candidate=d/"play_candidate.cpp"
        metadata=d/"metadata.json"
        execute(["python3",str(ROOT/"tools/generate_play_candidate.py"),
                 "--output",str(candidate),"--report",str(metadata)])
        original=d/"original.o"
        generated=d/"generated.o"
        executable=d/"compare-arm"
        execute(["arm-linux-gnueabihf-gcc","-std=c11","-O1",
                 "-Dplay=original_play","-Dstart=original_start",
                 "-c",str(ROOT/"examples/reverse/tictactoe.c"),"-o",str(original)])
        execute(["arm-linux-gnueabihf-g++","-std=c++17","-O1","-c",
                 str(candidate),"-o",str(generated)])
        execute(["arm-linux-gnueabihf-g++","-std=c++17","-O1",
                 str(ROOT/"tests/play_differential_harness.cpp"),
                 str(original),str(generated),"-o",str(executable)])
        behavior=json.loads(execute(["qemu-arm","-L","/usr/arm-linux-gnueabihf",str(executable)]))
        result={"platform":"qemu-arm, ARM Linux executable",
                "implementation":"original C versus generated C++",
                "cases":behavior["tested_cases"],"mismatches":behavior["mismatches"],
                "passed":behavior["passed"],"source_of_candidate":"ARM pattern inference plus structural C++ template",
                "scope":"Shared original winner; checks return and board[9] for every input",
                "byte_identical":False}
        if not result["passed"] or result["cases"]!=767637:
            raise AssertionError("ARM emulator differential check failed")
        p=Path(output)
        if not p.is_absolute():p=ROOT/p
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(result,indent=2))
        return result

if __name__=="__main__":
    run()
