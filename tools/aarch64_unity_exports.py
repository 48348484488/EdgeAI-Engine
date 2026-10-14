#!/usr/bin/env python3
"""Conservative static AArch64 symbol/CFG inventory of exported Unity engine APIs.

Runs no library code. Symbol-named engine entry points are not a gameplay
camera or entity-position provider.
"""
import argparse
import json
from pathlib import Path
from aarch64_branch_map import analyze_split
from aarch64_cfg import build_graph

LIBRARY = "libunity.so"
EXPORTS = ("UnitySendMessage", "UnityInitialize", "UnityShutdown", "JNI_OnLoad")


def inventory(apk, functions=EXPORTS):
    if not functions or len(functions)>8 or len(set(functions))!=len(functions):
        raise ValueError("requires unique nonempty bounded function set")
    if any(f not in EXPORTS for f in functions):
        raise ValueError("only known public engine exports can be selected")
    rows=[]
    for name in functions:
        scan=analyze_split(apk,name=LIBRARY,function=name,max_results=1000)
        graph=build_graph(scan)
        rows.append({
            "name":name,"entry":scan["entry"],"size_bytes":scan["size_bytes"],
            "control_transfers":scan["decoded_control_transfers"],
            "transfer_counts":scan["counts"],
            "candidate_blocks":graph["block_count"],
            "candidate_edges":graph["edge_count"],
            "entry_reachable_under_partial_model":graph["candidate_entry_reachable_blocks"],
            "external_direct_calls":sum(
                e["kind"]=="direct_call_site" and not e["target_in_symbol"]
                for e in graph["edges"]),
            "indirect_calls":graph["edge_kind_counts"].get("indirect_call_unresolved",0),
            "indirect_jumps":graph["edge_kind_counts"].get("indirect_jump_unresolved",0)
        })
    return {
        "status":"AARCH64_UNITY_ENGINE_STATIC_EXPORTS_PASS",
        "library":LIBRARY,"functions":rows,
        "function_count":len(rows),
        "executed_original_game":False,
        "unity_camera_located":False,
        "player_positions_located":False,
        "limits":[
            "Reads ELF symbol-sized ranges; no code execution.",
            "Control transfers recognized by a partial AArch64 decoder.",
            "CFG contains candidate paths only, indirect targets unresolved.",
            "UnitySendMessage export is not proof of an accessible game script bridge.",
            "No IL2CPP gameplay method, camera matrix, or player coordinate recovered."
        ]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("apk",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    report=inventory(args.apk)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
