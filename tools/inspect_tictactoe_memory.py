#!/usr/bin/env python3
"""Compila jogo da velha ARM e inventaria acessos reais de memoria via LLVM."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"examples"/"reverse"/"tictactoe.c"
spec=importlib.util.spec_from_file_location("edgeai_address",ROOT/"tools"/"arm_address_resolver.py")
address_tool=importlib.util.module_from_spec(spec)
spec.loader.exec_module(address_tool)
flow_spec=importlib.util.spec_from_file_location("edgeai_symbolic_flow",ROOT/"tools"/"arm_symbolic_flow.py")
symbolic_flow=importlib.util.module_from_spec(flow_spec)
flow_spec.loader.exec_module(symbolic_flow)
play_spec=importlib.util.spec_from_file_location("edgeai_play_evidence",ROOT/"tools"/"arm_play_evidence.py")
play_evidence=importlib.util.module_from_spec(play_spec)
play_spec.loader.exec_module(play_evidence)
branch_spec=importlib.util.spec_from_file_location("edgeai_compiled_branches",ROOT/"tools"/"arm_compiled_branches.py")
compiled_branches=importlib.util.module_from_spec(branch_spec)
branch_spec.loader.exec_module(compiled_branches)
paths_spec=importlib.util.spec_from_file_location("edgeai_play_paths",ROOT/"tools"/"arm_play_paths.py")
play_paths=importlib.util.module_from_spec(paths_spec)
paths_spec.loader.exec_module(play_paths)
constraints_spec=importlib.util.spec_from_file_location('edgeai_constraints',ROOT/'tools'/'arm_path_constraints.py')
constraints_tool=importlib.util.module_from_spec(constraints_spec)
constraints_spec.loader.exec_module(constraints_tool)

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
            instructions=[]
            for line in dump[start:end].splitlines():
                match=instruction_re.match(line)
                if not match:
                    continue
                pc,opcode,operands=match.groups()
                instructions.append({"pc":"0x"+pc,"mnemonic":opcode,"operands":operands.strip()})
            accesses=symbolic_flow.analyze(instructions)
            board_start=int(board.group(1),16)
            for access in accesses:
                numeric=int(access["resolved_address"],16) if access["resolved_address"] else None
                access["board_relation"]=("confirmed_address" if numeric is not None and board_start<=numeric<board_start+36 else "board_base_dynamic_index" if access.get("base_address")==hex(board_start) and numeric is None else "unresolved_or_other")
            item={"name":name,"address":hex(addr),
                  "memory_access_count":len(accesses),"accesses":accesses}
            if name=="play":
                item["register_evidence"]=play_evidence.report(instructions,board_start)
                item["control_flow"]=compiled_branches.analyze(instructions)
                item["path_events"]=play_paths.analyze(instructions,[a["pc"] for a in accesses if a["mnemonic"].startswith("str") and a["board_relation"]=="board_base_dynamic_index"])
                item["path_constraints"]=constraints_tool.explore(instructions)
            functions.append(item)
        if {item["name"] for item in functions}!={"start","play","winner"}:
            raise RuntimeError("expected game functions absent")
        return {"program":"compiled ARM32 tic-tac-toe","board_symbol_address":hex(int(board.group(1),16)),
                "functions":functions,
                "interpretation":"Known register bases can cross supported conditional branches; only a fully computed address in the board range is confirmed. Unsupported instructions invalidate register knowledge."}

if __name__=="__main__":
    print(json.dumps(evaluate(),indent=2,ensure_ascii=False))
