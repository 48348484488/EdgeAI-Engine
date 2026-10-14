#!/usr/bin/env python3
"""Annotate a static AArch64 candidate CFG with guarded ELF jump-table entries.

The table edges supplement (but never replace) unresolved BR edges.
They are independent *static candidates*, not observed runtime transitions.
"""
import argparse
import copy
import json
from pathlib import Path

MAX_EDGES=4096


def enrich(graph, table):
    if (graph.get("architecture")!="AArch64" or
        table.get("architecture")!="AArch64" or
        graph.get("function")!=table.get("function") or
        table.get("status")!="BOUNDED_AARCH64_STATIC_JUMP_TABLE_AUDIT"):
        raise ValueError("graph/table identity mismatch")
    if graph.get("code_executed") is not False or table.get("game_executed") is not False:
        raise ValueError("only read-only static input accepted")
    blocks=graph["blocks"]
    starts={}
    for b in blocks:
        pc=int(b["start"],16)
        if pc in starts:
            raise ValueError("duplicate basic block entry")
        starts[pc]=b
    if len(starts)!=graph["block_count"]:
        raise ValueError("invalid basic-block count")
    branch_blocks={}
    for b in blocks:
        if b["last_control_transfer"]=="BR":
            pc=int(b["last_instruction"],16)
            if pc in branch_blocks:
                raise ValueError("duplicate indirect branch tail")
            branch_blocks[pc]=b
    extra=[]
    covered_sites=0
    input_entries=0
    for site in table["sites"]:
        if site["status"]!="STATIC_CANDIDATES":
            continue
        pc=int(site["pc"],16)
        block=branch_blocks.get(pc)
        if block is None:
            raise ValueError("jump table not anchored to an unresolved BR block")
        entries=site["candidate_entries"]
        count=site["locally_bounded_entry_count"]
        if not 1<=count<=64 or count!=len(entries):
            raise ValueError("incomplete/oversized table")
        grouped={}
        used_indices=set()
        for row in entries:
            index=row["index"]
            target=int(row["candidate_target"],16)
            if type(index) is not int or index in used_indices or not 0<=index<count:
                raise ValueError("invalid/duplicate table index")
            used_indices.add(index)
            if target not in starts:
                raise ValueError("target not at an existing AArch64 basic-block boundary")
            grouped.setdefault(target,[]).append(index)
        if used_indices!=set(range(count)):
            raise ValueError("missing table index")
        for target,indices in sorted(grouped.items()):
            extra.append({
                "from":block["start"],"to":hex(target),
                "kind":"guarded_table_static_candidate",
                "indexes":sorted(indices),
                "dispatch_pc":hex(pc),
                "target_in_symbol":True,
                "evidence":"original_ELF_readonly_table_bytes_plus_local_guard",
                "runtime_path_confirmed":False
            })
        covered_sites+=1
        input_entries+=count
    if len(extra)>MAX_EDGES:
        raise ValueError("candidate edge count exceeds budget")
    if covered_sites!=table["table_sites_with_static_candidates"]:
        raise ValueError("static table site count mismatch")
    if input_entries!=table["candidate_entry_count"]:
        raise ValueError("static candidate entry count mismatch")

    original=graph["edges"]
    adjacency={pc:[] for pc in starts}
    for edge in [*original,*extra]:
        if not edge.get("target_in_symbol") or edge["kind"] in ("direct_call_site","indirect_call_unresolved"):
            continue
        frm=int(edge["from"],16)
        to=int(edge["to"],16)
        if frm not in adjacency or to not in starts:
            raise ValueError("edge references unknown block")
        adjacency[frm].append(to)
    root=int(graph["entry"],16)
    seen=set()
    frontier=[root]
    while frontier:
        point=frontier.pop()
        if point in seen:continue
        seen.add(point)
        frontier.extend(q for q in adjacency[point] if q not in seen)
    result=copy.deepcopy(graph)
    result.update({
        "status":"EDGEAI_AARCH64_STATIC_TABLE_GRAPH_ENRICHED",
        "original_candidate_edge_count":len(original),
        "guarded_table_entry_count":input_entries,
        "guarded_table_distinct_edge_count":len(extra),
        "augmented_candidate_edge_count":len(original)+len(extra),
        "entry_reachable_under_augmented_partial_model":len(seen),
        "candidate_entry_reachable_blocks":graph["candidate_entry_reachable_blocks"],
        "bounded_table_candidate_edges":extra,
        "game_executed":False,
        "runtime_reachability_proven":False,
        "limitations":[
            "BR remains unresolved in baseline CFG, extra edges are static candidate data.",
            "Index-dependent paths may not execute, alternate predecessors are not proven safe.",
            "All destinations must be existing block leaders and inside same ELF symbol.",
            "No Unity gameplay state or ESP evidence."
        ]
    })
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("cfg_json",type=Path)
    p.add_argument("table_json",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    result=enrich(json.loads(a.cfg_json.read_text()),json.loads(a.table_json.read_text()))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in
                      ("blocks","edges","bounded_table_candidate_edges")},indent=2))


if __name__=="__main__":main()
