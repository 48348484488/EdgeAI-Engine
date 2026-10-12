#!/usr/bin/env python3
"""Conservative ARM32 constant dataflow across direct CFG branches."""
import argparse
import importlib.util
import json
from collections import deque
from pathlib import Path
import struct

spec = importlib.util.spec_from_file_location("edgeai_semantics", Path(__file__).with_name("arm_semantics.py"))
sem = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sem)


def join(old, incoming):
    if old is None:
        return dict(incoming)
    return {k: v for k, v in old.items() if k in incoming and incoming[k] == v}


def analyze(data, entry, budget=4096):
    graph = sem.cfg.build(data, entry, "arm", budget)
    order, segments = sem.cfg.arm.exec_segments(data)
    nodes = {int(n["address"], 16) for n in graph["instructions"]}
    outgoing = {}
    for edge in graph["edges"]:
        outgoing.setdefault(int(edge["from"], 16), []).append((int(edge["to"], 16), edge["type"]))
    state = {entry: {}}
    queue = deque([entry])
    issues = set()
    steps = 0
    while queue:
        pc = queue.popleft()
        steps += 1
        if steps > budget * 40:
            raise sem.cfg.arm.ScanError("dataflow convergence budget exceeded")
        location = next((off + pc-base for off,base,size in segments if base <= pc and pc+4 <= base+size), None)
        if location is None:
            continue
        word = struct.unpack_from(order+"I",data,location)[0]
        decoded = sem.decode_arm(word,pc)
        op, cond = decoded["operation"], decoded["condition"]
        before = state[pc]
        after = dict(before)
        if op in ("MOV","ADD","SUB") and cond == "al":
            dst=decoded["destination"]
            if op == "MOV":
                value=decoded["immediate"]
            else:
                val=after.get(decoded["source"])
                value=None if val is None else ((val+decoded["immediate"]) if op=="ADD" else (val-decoded["immediate"]))&0xffffffff
            if value is None:
                after.pop(dst,None)
            else:
                after[dst]=value
            if decoded.get("sets_flags"):
                after.pop("$eq",None)
        elif op=="CMP" and cond=="al":
            val=after.get(decoded["source"])
            if val is None:
                after.pop("$eq",None)
            else:
                after["$eq"]=int(val==decoded["immediate"])
        elif op in ("B","BL"):
            pass
        elif op=="BX":
            continue
        else:
            issues.add(hex(pc))
            continue
        for dest,kind in outgoing.get(pc,[]):
            if kind.startswith("call"):
                continue
            if dest not in nodes:
                continue
            if op=="BL":
                # A call can change all caller-saved registers and flags.
                forwarded={k:v for k,v in after.items() if k in ("r4","r5","r6","r7","r8","r9","r10","r11")}
            elif op=="B" and cond in ("eq","ne"):
                eq=after.get("$eq")
                if eq is not None:
                    taken=(eq==1) if cond=="eq" else (eq==0)
                    if (kind=="taken") != taken:
                        continue
                forwarded=after
            elif cond=="al":
                forwarded=after
            else:
                issues.add(hex(pc))
                continue
            merged=join(state.get(dest),forwarded)
            if dest not in state or merged!=state[dest]:
                state[dest]=merged
                queue.append(dest)
    return {"entry":hex(entry),"mode":"arm","analyzed_addresses":len(state),
            "in_states":{hex(pc):{k:(hex(v) if k.startswith("r") else bool(v))
                                     for k,v in sorted(values.items())}
                         for pc,values in sorted(state.items())},
            "unsupported_addresses":sorted(issues),
            "limitations":"ARM immediate MOV ADD SUB CMP, direct B and BL only. Stops at unsupported instructions; joins keep only identical constants. Calls invalidate caller-saved registers."}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path)
    p.add_argument("--entry",required=True,type=lambda x:int(x,0))
    a=p.parse_args()
    try:
        if a.elf.stat().st_size>128*1024*1024:
            raise sem.cfg.arm.ScanError("file too large")
        result=analyze(a.elf.read_bytes(),a.entry)
    except (OSError,struct.error,sem.cfg.arm.ScanError) as e:
        p.exit(2,f"error: {e}\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    main()
