#!/usr/bin/env python3
"""Extract factual register-usage evidence from compiled ARM play(), not C reconstruction."""
import json
import re
from pathlib import Path

REGISTER=re.compile(r"(?<![A-Za-z0-9_])(r(?:1[0-5]|[0-9])|lr|sp|pc)(?![A-Za-z0-9_])",re.I)
MEMORY=re.compile(r"^(r\d+),\s*\[(r\d+),\s*(r\d+),\s*lsl\s*#2\]$")
COMPARE=re.compile(r"^(r\d+),\s*(?:#(0x[0-9a-fA-F]+|\d+)|r\d+)$")

def report(instructions,board_base):
    evidence=[]
    for ins in instructions:
        op=ins["mnemonic"].lower()
        args=ins["operands"]
        if op.startswith(("cmp","cmn","tst")):
            evidence.append({"pc":ins["pc"],"kind":"comparison","instruction":op+" "+args})
        if op.startswith(("b","cb")) and op not in ("bl","blx","bx"):
            evidence.append({"pc":ins["pc"],"kind":"branch","instruction":op+" "+args})
        match=MEMORY.match(args)
        if op.startswith(("ldr","str")) and match and match[2]=="r2" and match[3]=="r0":
            evidence.append({"pc":ins["pc"],"kind":"board_indexed_load" if op.startswith("ldr") else "board_indexed_store",
                             "base_register":"r2","index_register":"r0","scale_bytes":4,
                             "board_base":hex(board_base),
                             "requires_base_proof":True})
    return {"function":"play","input_registers":{"r0":"candidate position","r1":"candidate player"},
            "evidence":evidence,
            "pseudocode_outline":[
                "// r0 = candidate position, r1 = candidate player (AAPCS calling convention)",
                "// compare and branch instructions listed in evidence",
                "board[r0] // evidence for 4-byte indexed accesses when r2 == board",
                "// exact condition recovery is not yet proven"
            ],
            "warning":"Candidate parameter roles are inferred from AAPCS and memory operands; not a validated behavioral decompilation."}

if __name__=="__main__":
    raise SystemExit("Use report(instructions, board_base) with verified disassembly.")
