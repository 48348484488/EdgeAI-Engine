#!/usr/bin/env python3
"""Bounded *candidate* basic-block CFG from EdgeAI's AArch64 ELF symbol scan.

This is a static flow outline, NOT proof that an edge is feasible/executed.
Only the selected ELF function's declared symbol range is considered.
"""
import argparse
import json
from pathlib import Path
from aarch64_branch_map import analyze_split

CONDITIONAL = frozenset(("B.cond", "CBZ", "CBNZ", "TBZ", "TBNZ"))
NO_FALLTHROUGH = frozenset(("B", "BR", "RET"))
CALL = frozenset(("BL", "BLR"))
SUPPORTED = CONDITIONAL | NO_FALLTHROUGH | CALL
MAX_BLOCKS = 10000


def build_graph(scan):
    if scan.get("architecture") != "AArch64" or scan.get("sample_truncated"):
        raise ValueError("requires complete AArch64 control transfer scan")
    start = int(scan["entry"], 16)
    size = scan["size_bytes"]
    if size < 4 or size > 4*1024*1024 or size % 4 or start % 4:
        raise ValueError("invalid function alignment/bounds")
    end = start + size
    events = {}
    entries = scan["control_transfer_candidates"]
    if len(entries) != scan["decoded_control_transfers"]:
        raise ValueError("control transfers truncated or inconsistent")
    for ev in entries:
        pc = int(ev["pc"], 16)
        if pc % 4 or not start <= pc < end or pc in events:
            raise ValueError("invalid/duplicate control transfer PC")
        if ev["kind"] not in SUPPORTED:
            raise ValueError("unknown branch kind")
        target = int(ev["target"], 16) if ev["target"] is not None else None
        if target is not None and target % 4:
            raise ValueError("unaligned branch destination")
        if (ev["kind"] in ("RET", "BR", "BLR")) != (target is None):
            raise ValueError("bad branch target encoding")
        events[pc] = (ev["kind"], target)

    leaders = {start}
    for pc, (kind, target) in events.items():
        if target is not None and kind != "BL" and start <= target < end:
            leaders.add(target)
        if pc+4 < end:  # A new linear region starts after every control transfer.
            leaders.add(pc+4)
    points = sorted(leaders)
    if len(points) > MAX_BLOCKS:
        raise ValueError("basic-block budget exceeded")
    blocks = []
    edges = []
    by_start = set(points)

    def add_edge(source, target, kind):
        within = target is not None and start <= target < end
        if within and target not in by_start:
            raise ValueError("control transfer jumps into unknown block")
        edges.append({"from": hex(source), "to": hex(target) if target is not None else None,
                      "kind": kind, "target_in_symbol": within,
                      "evidence": "decoded_static_candidate"})

    for i, first in enumerate(points):
        last = points[i+1] if i+1 < len(points) else end
        tail = last - 4
        kind, target = events.get(tail, (None, None))
        blocks.append({"start":hex(first),"end_exclusive":hex(last),
                       "size_bytes":last-first,
                       "last_control_transfer":kind,
                       "last_instruction":hex(tail)})
        after = last if last < end else None
        if kind == "B":
            add_edge(first, target, "unconditional")
        elif kind in CONDITIONAL:
            add_edge(first, target, "taken_candidate")
            if after is not None: add_edge(first, after, "not_taken_candidate")
        elif kind == "BL":
            add_edge(first, target, "direct_call_site")
            if after is not None: add_edge(first, after, "call_return_candidate")
        elif kind == "BLR":
            add_edge(first, None, "indirect_call_unresolved")
            if after is not None: add_edge(first, after, "call_return_candidate")
        elif kind == "BR":
            add_edge(first, None, "indirect_jump_unresolved")
        elif kind == "RET":
            add_edge(first, None, "return_candidate")
        elif after is not None:
            # Unknown instructions were not fully decoded; these are only
            # *linear candidates*. They are NOT verified fallthrough edges.
            add_edge(first, after, "linear_candidate")

    graph = {int(p,16): [] for p in (b["start"] for b in blocks)}
    for edge in edges:
        if (edge["target_in_symbol"] and
            edge["kind"] not in ("direct_call_site", "indirect_call_unresolved")):
            graph[int(edge["from"],16)].append(int(edge["to"],16))
    seen = set()
    todo = [start]
    while todo:
        pc = todo.pop()
        if pc in seen: continue
        seen.add(pc)
        todo.extend(q for q in graph[pc] if q not in seen)

    backwards = [e for e in edges
                 if e["target_in_symbol"] and
                    int(e["to"],16) <= int(e["from"],16) and
                    e["kind"] in ("unconditional","taken_candidate","not_taken_candidate")]
    counts = {}
    for e in edges: counts[e["kind"]] = counts.get(e["kind"],0)+1
    return {
        "architecture":"AArch64",
        "function":scan["function"],"entry":scan["entry"],
        "symbol_size_bytes":size,
        "block_count":len(blocks),
        "edge_count":len(edges),
        "candidate_entry_reachable_blocks":len(seen),
        "not_entry_reachable_under_partial_model":len(blocks)-len(seen),
        "backward_edge_candidates":len(backwards),
        "edge_kind_counts":counts,
        "blocks":blocks,
        "edges":edges,
        "code_executed":False,
        "reachability_proven":False,
        "loop_iteration_count_proven":False,
        "limitations":[
            "Linear AArch64 basic blocks within a named ELF symbol's declared range.",
            "Unrecognized instruction effects may invalidate speculative fallthrough.",
            "Indirect jumps/calls have unknown targets; direct call destinations are not traversed.",
            "Potential entry-reachability, backward edges and return edges are not execution proof.",
            "Not a decompiler, player/camera resolver, or game protection bypass."
        ]
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("apk",type=Path)
    p.add_argument("--library",default="libloader.so",choices=("libloader.so","libunity.so","libil2cpp.so"))
    p.add_argument("--function",default="JNI_OnLoad")
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    scan=analyze_split(args.apk,args.library,args.function,max_results=1000)
    report=build_graph(scan)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("blocks","edges")},indent=2))


if __name__=="__main__": main()
