"""Infer specific play() control-flow facts from LLVM ARM32 disassembly."""
import re
import subprocess
import tempfile
from pathlib import Path

def infer(source):
    with tempfile.TemporaryDirectory() as d:
        exe=Path(d)/"game.elf"
        subprocess.run(["clang","--target=armv7-none-eabi","-marm","-O1","-fno-inline",
                        "-nostdlib","-fuse-ld=lld","-Wl,-Ttext=0x1000","-Wl,-e=start",
                        str(source),"-o",str(exe)],check=True,capture_output=True,text=True)
        disasm=subprocess.run(["llvm-objdump","-d",str(exe)],check=True,
                              capture_output=True,text=True).stdout
    block=re.search(r"(?ms)^[0-9a-fA-F]+ <play>:\n(.*?)(?=^[0-9a-fA-F]+ <|\Z)",disasm)
    if not block: raise ValueError("play symbol not found")
    ins=[]
    for line in block[1].splitlines():
        m=re.match(r"^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F]+\s+([a-z0-9]+)\s*(.*)$",line)
        if m: ins.append((m[2],m[3].split("@")[0].strip()))
    limits=[int(m[1],0) for op,args in ins
            if op=="cmp" and (m:=re.fullmatch(r"r0, #(0x[0-9a-fA-F]+|[0-9]+)",args))]
    evidence={"unsigned_upper_bound":len(limits)==1 and any(op=="bhi" for op,_ in ins),
              "empty_cell_guard":("cmp","r3, #0") in ins and any(op=="beq" for op,_ in ins),
              "rejection_minus_one":("mvn","r0, #0") in ins,
              "winner_tail_jump":any(op=="b" and "<winner>" in args for op,args in ins)}
    if not all(evidence.values()): raise ValueError("ARM pattern incomplete: "+str(evidence))
    return {"max_position":limits[0],"empty_value":0,"rejection_value":-1,
            "success_target":"winner","pattern_evidence":evidence}
