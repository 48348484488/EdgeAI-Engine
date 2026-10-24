#!/usr/bin/env python3
"""Check original ARM64 machine-code stdout against source-blind recovered C++.

Requires original stdout obtained by actually executing the immutable,
sha256-pinned 2048 AArch64 ELF under QEMU user-mode, not the source oracle.
Fails closed if any input, ELF, file hash, output length or output byte differs.
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXPECTED="a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b"

def compare(artifact,report,library=None):
    artifact=Path(artifact)
    library=Path(library) if library else ROOT/"batch_v14/recovered_candidates.so"
    if not library.is_file():
        raise FileNotFoundError("missing regenerated C++ library "+str(library))
    manifest=artifact/"original_stdout_manifest.json"
    if not manifest.is_file():
        manifest=artifact/"output/original_stdout_manifest.json"
    if not manifest.is_file():
        raise FileNotFoundError("missing original ELF QEMU run manifest")
    source=json.loads(manifest.read_text())
    declared=json.loads((ROOT/"qemu_real/scenarios.json").read_text())
    if (source["elf_sha256"]!=EXPECTED or
        declared["benchmark_elf_sha256"]!=EXPECTED or
        hashlib.sha256((ROOT/"bin/2048-arm64-stripped.elf").read_bytes()).hexdigest()!=EXPECTED):
        raise ValueError("original ELF SHA256 mismatch")
    cases=source["cases"]
    if len(cases)!=21 or len(declared["cases"])!=21:
        raise ValueError("expected exactly 21 original QEMU cases")
    with tempfile.TemporaryDirectory(prefix="edgeai-v14-real-qemu-") as temp:
        tmp=Path(temp)
        for mode,driver in (("CELL","generated_driver.cpp"),("BOARD","generated_board_driver.cpp")):
            subprocess.run(["g++","-std=c++17","-O2",str(ROOT/"print_v14"/driver),
                            str(library),"-Wl,-rpath,"+str(library.parent),
                            "-o",str(tmp/mode)],check=True,capture_output=True)
        compared=0
        total=0
        digests=[]
        for i,(case,expected) in enumerate(zip(cases,declared["cases"])):
            if case["case"]!=i or case["input"]!=expected:
                raise ValueError("original QEMU input/provenance mismatch: "+str(i))
            output=manifest.parent/f"original_case_{i:02d}.bin"
            if not output.is_file():raise FileNotFoundError(str(output))
            original=output.read_bytes()
            if len(original)!=case["bytes"] or hashlib.sha256(original).hexdigest()!=case["sha256"]:
                raise ValueError("original QEMU machine output tampered at "+str(i))
            mode=expected["type"]
            if mode=="CELL" and expected["entry"]=="0x401004":
                args=[str(expected[x]) for x in ("value","row","col")]
            elif mode=="BOARD" and expected["entry"]=="0x401404" and len(expected["board"])==16:
                args=list(map(str,expected["board"]))
            else:
                raise ValueError("unsupported machine ABI case")
            generated=subprocess.check_output([str(tmp/mode),*args],timeout=10)
            if generated!=original:
                mismatch=next((j for j,(a,b) in enumerate(zip(generated,original)) if a!=b),
                              min(len(generated),len(original)))
                raise AssertionError(f"original ARM64 machine output differs from C++: case={i},byte={mismatch}")
            compared+=1
            total+=len(original)
            digests.append({"case":i,"mode":mode,"bytes":len(original),"sha256":case["sha256"]})
    results={"method":"unchanged original stripped AArch64 ELF executed under QEMU user-mode",
             "source_used_for_comparison":False,"game_symtab_used":False,
             "ELF_sha256":EXPECTED,"cases_compared":compared,"bytes_equal":total,
             "mismatches":0,"cases":digests,"full_game_reconstructed":False}
    report=Path(report)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(results,indent=2)+"\n")
    return results

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    out=compare(a.artifact,a.report)
    print(json.dumps({k:out[k] for k in ("cases_compared","bytes_equal","mismatches")},indent=2))
