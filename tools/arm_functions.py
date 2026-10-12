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
    pending=[(entry,mode)]
    candidates={}
    calls=set()
    while pending:
        start,current_mode=pending.pop(0)
        if (start,current_mode) in candidates:
            continue
        if len(candidates)>=max_functions:
            raise cfg.arm.ScanError("function budget exceeded")
        graph=cfg.build(data,start,current_mode,max_instructions)
        candidates[(start,current_mode)]=graph
        for edge in graph["edges"]:
            if not edge["type"].startswith("call"):
                continue
            src,dst=int(edge["from"],16),int(edge["to"],16)
            destination_mode=edge["type"].partition(":")[2] or current_mode
            calls.add((start,current_mode,src,dst,destination_mode))
            if (dst,destination_mode) not in candidates and (dst,destination_mode) not in pending:
                pending.append((dst,destination_mode))
    return {
        "architecture":"ARM32","mode":mode,"seed":hex(entry),
        "candidate_count":len(candidates),
        "candidates":[{
            "address":hex(addr), "mode":candidate_mode,
            "basis":"user_seed" if (addr,candidate_mode)==(entry,mode) else "direct_call_target",
            "visited_instructions":graph["instruction_count"],
            "unresolved_targets":graph["unresolved_targets"]
        } for (addr,candidate_mode),graph in sorted(candidates.items())],
        "calls":[{"caller_candidate":hex(owner),"caller_mode":origin_mode,"call_site":hex(site),"target_candidate":hex(dst),"target_mode":destination_mode}
                 for owner,origin_mode,site,dst,destination_mode in sorted(calls)],
        "limitations":"Call targets are candidates, not proven functions. Indirect BLX calls, general Thumb-2 decoding, tail calls, data flow, and decompilation are not supported."
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
