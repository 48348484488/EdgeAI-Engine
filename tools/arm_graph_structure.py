"""Conservative structural summaries of an ARM CFG; not source decompilation."""
from collections import defaultdict, deque

def analyze(graph):
    nodes={int(n["address"],16):n for n in graph["nodes"]}
    edges=defaultdict(list)
    for e in graph["edges"]:
        src,dst=int(e["from"],16),int(e["to"],16)
        if src in nodes and e["type"]!="call":
            edges[src].append((dst,e["type"]))
    entry=int(graph["entry"],16)
    reachable=set()
    pending=deque([entry])
    while pending:
        pc=pending.popleft()
        if pc in reachable or pc not in nodes: continue
        reachable.add(pc)
        pending.extend(dst for dst,_ in edges[pc])
    decisions=[]
    for pc in sorted(reachable):
        successors=[(d,t) for d,t in edges[pc] if t in ("taken","fallthrough")]
        if len(successors)==2 and {t for _,t in successors}=={"taken","fallthrough"}:
            decisions.append({"address":hex(pc),"condition":nodes[pc].get("condition"),
                              "taken":hex(next(d for d,t in successors if t=="taken")),
                              "fallthrough":hex(next(d for d,t in successors if t=="fallthrough"))})
    return {"entry":graph["entry"],"reachable_nodes":len(reachable),
            "decision_candidates":decisions,
            "returns":[hex(pc) for pc in sorted(reachable) if nodes[pc].get("op")=="indirect_branch" and nodes[pc].get("register") in ("r14","lr")],
            "unresolved_edges":[{"from":hex(pc),"to":hex(d),"type":t} for pc in sorted(reachable) for d,t in edges[pc] if d not in nodes],
            "unsupported_reachable":[hex(pc) for pc in sorted(reachable) if nodes[pc]["op"]=="unsupported"],
            "status":"structural-candidates-only"}
