#!/usr/bin/env python3
"""Compara chamadas diretas da EdgeAI com LLVM Objdump em ELF ARM reais."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("edgeai_functions",ROOT/"tools"/"arm_functions.py")
fn=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fn)

CASES={
 "arm":("arm",".syntax unified\n.arm\n.global start\n.type start,%function\nstart:\n bl callee\n bx lr\ncallee:\n bx lr\n"),
 "thumb":("thumb",".syntax unified\n.thumb\n.global start\n.thumb_func\nstart:\n bl callee\n bx lr\n.thumb_func\ncallee:\n bx lr\n"),
 "thumb_to_arm":("thumb",".syntax unified\n.thumb\n.global start\n.thumb_func\nstart:\n blx callee\n bx lr\n.p2align 2\n.arm\ncallee:\n bx lr\n")
}
CALL=re.compile(r"^\s*([0-9a-f]+):\s+[0-9a-f]+\s+(?:blx|bl)\s+0x([0-9a-f]+)\b",re.I|re.M)

def validate(clang="clang",objdump="llvm-objdump"):
    cases=[]
    with tempfile.TemporaryDirectory() as d:
        for name,(mode,source) in CASES.items():
            asm=Path(d)/(name+".s")
            elf=Path(d)/(name+".elf")
            asm.write_text(source,encoding="utf-8")
            subprocess.run([clang,"--target=armv7-none-eabi","-fuse-ld=lld","-nostdlib",
                            "-Wl,-Ttext=0x1000","-Wl,-e,start",str(asm),"-o",str(elf)],
                           check=True,capture_output=True,text=True)
            output=subprocess.run([objdump,"-d",str(elf)],check=True,
                                  capture_output=True,text=True).stdout
            expected={(int(a,16),int(b,16)) for a,b in CALL.findall(output)}
            if not expected:
                raise ValueError("no reference calls in "+name)
            result=fn.discover(elf.read_bytes(),0x1000,mode)
            observed={(int(x["call_site"],16),int(x["target_candidate"],16))
                      for x in result["calls"]}
            cases.append({"name":name,"reference":len(expected),"detected":len(observed),
                          "correct":len(expected&observed),
                          "false_positives":len(observed-expected),
                          "false_negatives":len(expected-observed),
                          "match":expected==observed})
    return {"reference":"llvm-objdump","input":"clang-assembled ELF32 ARM programs",
            "scope":"3 small direct-call fixtures, not overall decompiler accuracy",
            "cases":cases,"passed":all(x["match"] for x in cases)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clang",default="clang")
    p.add_argument("--llvm-objdump",default="llvm-objdump")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    report=validate(args.clang,args.llvm_objdump)
    content=json.dumps(report,indent=2,ensure_ascii=False)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(content,encoding="utf-8")
    print(content,end="")
    if not report["passed"]:
        raise SystemExit(1)
if __name__=="__main__":
    main()
