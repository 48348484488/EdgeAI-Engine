#!/usr/bin/env python3
"""Compila um jogo da velha C para ARM32 e valida chamadas reais com LLVM."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("edgeai_arm_functions",ROOT/"tools"/"arm_functions.py")
functions=importlib.util.module_from_spec(spec)
spec.loader.exec_module(functions)

def run():
    source=ROOT/"examples"/"reverse"/"tictactoe.c"
    with tempfile.TemporaryDirectory() as folder:
        binary=Path(folder)/"tictactoe-arm.elf"
        subprocess.run([
            "clang","--target=armv7-none-eabi","-marm","-O1",
            "-fno-inline","-nostdlib","-fuse-ld=lld",
            "-Wl,-Ttext=0x1000","-Wl,-e,start",
            str(source),"-o",str(binary)
        ],check=True,capture_output=True,text=True)
        disassembly=subprocess.run(["llvm-objdump","-d",str(binary)],
                                   check=True,capture_output=True,text=True).stdout
        symbols=dict((name,int(address,16)) for address,name in
                     re.findall(r"^([0-9a-fA-F]+) <(winner|play|start)>:",disassembly,re.M))
        if set(symbols)!={"winner","play","start"}:
            raise RuntimeError("LLVM did not find the expected game functions")
        calls={(int(site,16),int(target,16)) for site,target in
               re.findall(r"^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F]+\s+bl\s+0x([0-9a-fA-F]+)",disassembly,re.M)}
        calls_from_start={(a,b) for a,b in calls if a>=symbols["start"]}
        if not calls_from_start: raise RuntimeError("no direct calls identified by LLVM")
        edgeai=functions.discover(binary.read_bytes(),symbols["start"],"arm")
        actual={(int(x["call_site"],16),int(x["target_candidate"],16))
                for x in edgeai["calls"] if int(x["call_site"],16)>=symbols["start"]}
        return {"game":"Jogo da velha (C, compilado para ARM32)",
                "real_binary":True,"reference":"LLVM Objdump",
                "source_functions":{k:hex(v) for k,v in sorted(symbols.items())},
                "expected_calls":len(calls_from_start),
                "correct_calls":len(calls_from_start & actual),
                "false_positives":len(actual-calls_from_start),
                "false_negatives":len(calls_from_start-actual),
                "matched":actual==calls_from_start,
                "limitations":"Only direct BL sites in start are compared. A tail branch from play to winner is not a BL call."}

if __name__=="__main__":
    result=run()
    print(json.dumps(result,indent=2,ensure_ascii=False))
    raise SystemExit(0 if result["matched"] else 1)
