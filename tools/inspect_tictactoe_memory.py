#!/usr/bin/env python3
"""Compila jogo da velha ARM e inventaria acessos reais de memoria via LLVM."""
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"examples"/"reverse"/"tictactoe.c"

def evaluate():
    with tempfile.TemporaryDirectory() as directory:
        executable=Path(directory)/"game.elf"
        subprocess.run(["clang","--target=armv7-none-eabi","-marm","-O1",
                        "-fno-inline","-nostdlib","-fuse-ld=lld",
                        "-Wl,-Ttext=0x1000","-Wl,-e,start",
                        str(SOURCE),"-o",str(executable)],check=True,capture_output=True,text=True)
        dump=subprocess.run(["llvm-objdump","-d",str(executable)],
                            check=True,capture_output=True,text=True).stdout
        sym=subprocess.run(["llvm-nm","-n",str(executable)],
                           check=True,capture_output=True,text=True).stdout
        symbol_re=re.compile(r"^([0-9a-fA-F]+) <([^>]+)>:",re.M)
        instruction_re=re.compile(r"^\s*([0-9a-fA-F]+):\s+[0-9a-fA-F]+\s+([a-zA-Z][a-zA-Z0-9.]*)\s*(.*)$")
        locations=[(m.start(),int(m.group(1),16),m.group(2)) for m in symbol_re.finditer(dump)]
        board=re.search(r"^([0-9a-fA-F]+)\s+[A-Za-z]\s+board$",sym,re.M)
        if board is None:
            raise RuntimeError("board symbol absent")
        functions=[]
        for i,(start,addr,name) in enumerate(locations):
            if name not in ("start","play","winner"):
                continue
            end=locations[i+1][0] if i+1<len(locations) else len(dump)
            accesses=[]
            for line in dump[start:end].splitlines():
                match=instruction_re.match(line)
                if not match:
                    continue
                pc,opcode,operands=match.groups()
                if opcode.startswith(("ldr","str")):
                    accesses.append({"pc":"0x"+pc,"mnemonic":opcode,"operands":operands.strip(),
                                    "is_board_access":"unproven"})
            functions.append({"name":name,"address":hex(addr),
                              "memory_access_count":len(accesses),"accesses":accesses})
        if {item["name"] for item in functions}!={"start","play","winner"}:
            raise RuntimeError("expected game functions absent")
        return {"program":"compiled ARM32 tic-tac-toe","board_symbol_address":hex(int(board.group(1),16)),
                "functions":functions,
                "interpretation":"LDR/STR instructions are verified by LLVM; their relationship to board is not proven by these instructions alone."}

if __name__=="__main__":
    print(json.dumps(evaluate(),indent=2,ensure_ascii=False))
