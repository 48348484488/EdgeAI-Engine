#!/usr/bin/env python3
"""Compile ARM evidence, generate constrained candidate, run native differential tests."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def run(output=Path("results/play_reconstruction_test.json")):
    with tempfile.TemporaryDirectory() as t:
        directory=Path(t)
        candidate=directory/"play_candidate.cpp"
        metadata=directory/"metadata.json"
        def invoke(argv):
            return subprocess.run(argv,check=True,capture_output=True,text=True,cwd=ROOT)
        invoke(["python3",str(ROOT/"tools/generate_play_candidate.py"),
                "--output",str(candidate),"--report",str(metadata)])
        original=directory/"original.o"
        rebuilt=directory/"candidate.o"
        arm_candidate=directory/"candidate_arm.o"
        harness=directory/"test"
        invoke(["clang","-std=c11","-O1","-Dplay=original_play",
                "-Dstart=original_start","-c",str(ROOT/"examples/reverse/tictactoe.c"),
                "-o",str(original)])
        invoke(["clang++","-std=c++17","-O1","-c",str(candidate),"-o",str(rebuilt)])
        invoke(["clang++","--target=armv7-none-eabi","-marm","-O1",
                "-ffreestanding","-fno-exceptions","-fno-rtti",
                "-c",str(candidate),"-o",str(arm_candidate)])
        invoke(["clang++","-std=c++17","-O1",str(ROOT/"tests/play_differential_harness.cpp"),
                str(original),str(rebuilt),"-o",str(harness)])
        behavior=json.loads(invoke([str(harness)]).stdout.strip())
        info=json.loads(metadata.read_text(encoding="utf-8"))
        report={"game":"compiled ARM32 tic-tac-toe","function":"play",
                "candidate_generation":info["generation"],
                "evidence":info["binary_evidence"],
                "source_assumptions":info["not_inferred_from_binary"],
                "inferred_from_binary":info["inferred_from_binary"],
                "intermediate_representation":info["intermediate_representation"],
                "arm32_candidate_compiled":arm_candidate.is_file(),
                "native_behavior_test":behavior,
                "binary_bytes_compared":False,
                "caveat":"Bounds, zero-cell guard and rejection value are pattern-inferred from ARM, while structure and winner implementation remain shared/template-based; not autonomous decompilation."}
        output=Path(output)
        if not output.is_absolute():output=ROOT/output
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(json.dumps(report,indent=2,ensure_ascii=False))
        if not behavior["passed"] or behavior["tested_cases"]!=767637:
            raise RuntimeError("candidate failed exhaustive differential suite")
        return report

if __name__=="__main__":
    run()
