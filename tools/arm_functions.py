#!/usr/bin/env python3
"""Discover ARM32 function *candidates* via direct BL calls and an explicit seed."""
import argparse
import importlib.util
import json
from pathlib import Path

spec=importlib.util.spec_from_file_location("edgeai_cfg",Path(__file__).with_name("arm_cfg.py"))
cfg=importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)

def discover(data, entry, mode="arm", max_functions=128, max_instructions=4096):
    if mode not in ("arm","thumb") or not 1<=max_functions<=4096:
        raise cfg.arm.ScanError("invalid mode or function budget")
    # A direct call target is a candidate, never a confirmed function boundary.
    pending=[entry]
    candidates={}
    calls=set()
    while pending:
        start=pending.pop(0)
        if start in candidates:
            continue
        if len(candidates)>=max_functions:
            raise cfg.arm.ScanError("function budget exceeded")
        graph=cfg.build(data,start,mode,max_instructions)
        candidates[start]=graph
        for edge in graph["edges"]:
            if edge["type"]!="call":
                continue
            src,dst=int(edge["from"],16),int(edge["to"],16)
            calls.add((start,src,dst))
            if dst not in candidates and dst not in pending:
                pending.append(dst)
    return {
        "architecture":"ARM32","mode":mode,"seed":hex(entry),
        "candidate_count":len(candidates),
        "candidates":[{
            "address":hex(addr),
            "basis":"user_seed" if addr==entry else "direct_BL_target",
            "visited_instructions":graph["instruction_count"],
            "unresolved_targets":graph["unresolved_targets"]
        } for addr,graph in sorted(candidates.items())],
        "calls":[{"caller_candidate":hex(owner),"call_site":hex(site),"target_candidate":hex(dst)}
                 for owner,site,dst in sorted(calls)],
        "limitations":"Call targets are candidates, not proven functions. BLX and Thumb-2 calls, cross-mode calls, tail calls, data flow, and decompilation are not supported."
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("file",type=Path)
    p.add_argument("--entry",required=True,type=lambda x:int(x,0))
    p.add_argument("--mode",choices=["arm","thumb"],required=True)
    p.add_argument("--max-functions",type=int,default=128)
    p.add_argument("--max-instructions",type=int,default=4096)
    a=p.parse_args()
    try:
        if a.file.stat().st_size>128*1024*1024:
            raise cfg.arm.ScanError("file exceeds 128 MiB")
        out=discover(a.file.read_bytes(),a.entry,a.mode,a.max_functions,a.max_instructions)
    except (OSError,cfg.arm.ScanError) as e:
        p.exit(2,f"error: {e}\n")
    print(json.dumps(out,indent=2))

if __name__=="__main__":
    main()
