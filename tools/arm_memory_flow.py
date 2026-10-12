#!/usr/bin/env python3
"""Memory-aware ARM32 CFG dataflow, deliberately conservative."""
import argparse
import importlib.util
import json
from collections import deque
from pathlib import Path
import struct

def load(name):
    path=Path(__file__).with_name(name+".py")
    spec=importlib.util.spec_from_file_location("edgeai_"+name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

flow=load("arm_dataflow")
mem=load("arm_memory")

def merge(old,new):
    if old is None:
        return dict(new)
    return {k:v for k,v in old.items() if k in new and new[k]==v}

def analyze(data,entry,budget=4096):
    cfg=flow.sem.cfg.build(data,entry,"arm",budget)
    order,segs=flow.sem.cfg.arm.exec_segments(data)
    nodes={int(n["address"],16) for n in cfg["instructions"]}
    outgoing={}
    for edge in cfg["edges"]:
        outgoing.setdefault(int(edge["from"],16),[]).append((int(edge["to"],16),edge["type"]))
    states={entry:{"regs":{},"memory":{}}}
    queue=deque([entry])
    unsupported=set()
    steps=0
    while queue:
        pc=queue.popleft()
        steps+=1
        if steps>budget*40: raise flow.sem.cfg.arm.ScanError("convergence budget exceeded")
        off=next((o+pc-base for o,base,size in segs if base<=pc and pc+4<=base+size),None)
        if off is None: continue
        word=struct.unpack_from(order+"I",data,off)[0]
        decoded=flow.sem.decode_arm(word,pc)
        regs=dict(states[pc]["regs"])
        memory=dict(states[pc]["memory"])
        op,cond=decoded["operation"],decoded["condition"]
        access=mem.decode_memory(word)
        if access and cond=="al":
            base=regs.get(access["base"])
            address=None if base is None else (base+access["offset"])&0xffffffff
            target=access["register"]
            if access["operation"]=="STR":
                if address is None:
                    memory.clear()
                else:
                    value=regs.get(target)
                    if value is None: memory.pop(address,None)
                    else: memory[address]=value
            else:
                value=memory.get(address) if address is not None else None
                if value is None: regs.pop(target,None)
                else: regs[target]=value
        elif cond=="al" and op in ("MOV","ADD","SUB"):
            dest=decoded["destination"]
            if op=="MOV": value=decoded["immediate"]
            else:
                original=regs.get(decoded["source"])
                value=None if original is None else (
                    original+decoded["immediate"] if op=="ADD" else original-decoded["immediate"])&0xffffffff
            if value is None: regs.pop(dest,None)
            else: regs[dest]=value
            if decoded.get("sets_flags"): regs.pop("$eq",None)
        elif cond=="al" and op=="CMP":
            src=regs.get(decoded["source"])
            if src is None: regs.pop("$eq",None)
            else: regs["$eq"]=int(src==decoded["immediate"])
        elif op in ("B","BL"): pass
        elif op=="BX": continue
        else:
            unsupported.add(hex(pc))
            continue
        for dest,kind in outgoing.get(pc,[]):
            if kind.startswith("call") or dest not in nodes: continue
            if op=="B" and cond in ("eq","ne"):
                eq=regs.get("$eq")
                if eq is not None:
                    expected=(eq==1) if cond=="eq" else (eq==0)
                    if (kind=="taken")!=expected: continue
            elif cond!="al":
                unsupported.add(hex(pc))
                continue
            if op=="BL":
                regs_out={k:v for k,v in regs.items() if k in ("r4","r5","r6","r7","r8","r9","r10","r11")}
                # Calls may modify all tracked memory.
                mem_out={}
            else:
                regs_out=regs
                mem_out=memory
            previous=states.get(dest)
            merged={"regs":merge(None if previous is None else previous["regs"],regs_out),
                    "memory":merge(None if previous is None else previous["memory"],mem_out)}
            if merged!=previous:
                states[dest]=merged
                queue.append(dest)
    return {"entry":hex(entry),"mode":"arm","in_states":{
        hex(pc):{"registers":{k:hex(v) if k.startswith("r") else bool(v) for k,v in state["regs"].items()},
                 "memory":{hex(k):hex(v) for k,v in state["memory"].items()}}
        for pc,state in sorted(states.items())},
        "unsupported_addresses":sorted(unsupported),
        "limitations":"ARM immediate arithmetic and word LDR/STR pre-indexed only; merges retain matching constants; calls invalidate memory; unsupported paths stop. Not alias or whole-program analysis."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path)
    p.add_argument("--entry",required=True,type=lambda v:int(v,0))
    a=p.parse_args()
    try:
        if a.elf.stat().st_size>128*1024*1024: raise flow.sem.cfg.arm.ScanError("file too large")
        result=analyze(a.elf.read_bytes(),a.entry)
    except (OSError,struct.error,flow.sem.cfg.arm.ScanError) as error:
        p.exit(2,f"error: {error}\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
