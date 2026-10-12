"""Trace branch destinations to rejection and board-write evidence in ARM play."""
import re
from collections import deque

COND={"beq","bne","bhi","bls","bge","blt","bgt","ble","bcs","bcc"}
TARGET=re.compile(r"^(0x[0-9a-fA-F]+)")

def analyze(instructions, board_write_pcs):
    by_pc={int(x["pc"],16):x for x in instructions}
    pcs=sorted(by_pc)
    next_pc={pc:pcs[i+1] for i,pc in enumerate(pcs[:-1])}
    writes={int(x,16) for x in board_write_pcs}
    def successors(pc):
        ins=by_pc[pc];op=ins["mnemonic"].lower();args=ins["operands"]
        if op=="bx" or op=="pop":return []
        if op=="b" or op in COND:
            m=TARGET.match(args)
            target=int(m[1],16) if m else None
            choices=[target] if op=="b" else [target,next_pc.get(pc)]
            return [p for p in choices if p in by_pc]
        return [next_pc[pc]] if pc in next_pc else []
    def walk(start):
        seen=set();stack=[start];out=set()
        while stack:
            pc=stack.pop()
            if pc not in by_pc or pc in seen:continue
            seen.add(pc)
            ins=by_pc[pc];op=ins["mnemonic"].lower()
            if pc in writes:out.add("board_write")
            if op=="mvn" and ins["operands"].strip()=="r0, #0":
                out.add("sets_minus_one")
            if op=="b" and "<winner>" in ins["operands"]:
                out.add("winner_tail_jump")
            if op=="bx" and ins["operands"].strip()=="lr":
                out.add("return")
            stack.extend(successors(pc))
        return sorted(out)
    forks=[]
    for pc in pcs:
        ins=by_pc[pc];op=ins["mnemonic"].lower()
        if op not in COND:continue
        m=TARGET.match(ins["operands"])
        if m is None:continue
        taken=int(m[1],16);fall=next_pc.get(pc)
        if taken not in by_pc or fall not in by_pc:continue
        forks.append({"pc":hex(pc),"condition":op[1:],
                      "taken":{"pc":hex(taken),"reachable_events":walk(taken)},
                      "fallthrough":{"pc":hex(fall),"reachable_events":walk(fall)}})
    return {"function":"play","forks":forks,
            "limitation":"May-events per path, no register-state or path-feasibility proof."}
