"""Bounded path exploration with equality constraints from CMP and BEQ/BNE.

Tracks comparisons of a register with immediate. Unsupported operations kill
the comparison; distinct branches with incompatible constraints are pruned.
"""
import re
from collections import deque

IMM=re.compile(r"^(r\d+),\s*#(0x[0-9a-fA-F]+|\d+)$")
TARGET=re.compile(r"^0x([0-9a-fA-F]+)")
def explore(instructions, max_states=10000):
    nodes={int(x["pc"],16):x for x in instructions}
    pcs=sorted(nodes)
    nxt={p:pcs[i+1] for i,p in enumerate(pcs[:-1])}
    queue=deque([(pcs[0],None,{})]) if pcs else deque()
    visited=set()
    terminal=[]
    pruned=0
    while queue:
        if len(visited)>max_states:
            raise ValueError("path exploration budget exceeded")
        pc,comparison,constraints=queue.popleft()
        if pc not in nodes:continue
        key=(pc,comparison,tuple(sorted((k,v[0],v[1]) for k,v in constraints.items())))
        if key in visited:continue
        visited.add(key)
        ins=nodes[pc]
        op=ins["mnemonic"].lower()
        args=ins["operands"]
        if op=="cmp":
            m=IMM.fullmatch(args)
            comparison=(m[1],int(m[2],0)) if m else None
        elif op in ("beq","bne"):
            m=TARGET.match(args)
            if comparison is None or not m:
                comparison=None
            else:
                reg,value=comparison
                for taken,dst in ((True,int(m[1],16)),(False,nxt.get(pc))):
                    equality=(op=="beq")==taken
                    current=dict(constraints)
                    equal,not_equal=current.get(reg,(None,()))
                    if equality:
                        if (equal is not None and equal!=value) or value in not_equal:
                            pruned+=1;continue
                        current[reg]=(value,not_equal)
                    else:
                        if equal==value:
                            pruned+=1;continue
                        current[reg]=(equal,tuple(sorted(set(not_equal)|{value})))
                    if dst is not None:queue.append((dst,comparison,current))
                continue
        elif op in ("ldr","ldrb","mov","movw","movt","add","sub"):
            dest=args.split(",",1)[0].strip()
            constraints={reg:val for reg,val in constraints.items() if reg!=dest}
            comparison=None
        elif op=="bx" or op=="pop":
            terminal.append({"pc":hex(pc),"constraints":constraints})
            continue
        elif op not in ("b","str","cmp","tst","beq","bne"):
            comparison=None
            # Unknown writes/side effects could invalidate register constraints.
            constraints={}
        if op in ("bhi","bls","bge","blt","bgt","ble","bcs","bcc","bmi","bpl"):
            m=TARGET.match(args)
            if m and int(m[1],16) in nodes:
                queue.append((int(m[1],16),None,dict(constraints)))
            if pc in nxt:
                queue.append((nxt[pc],None,dict(constraints)))
        elif op=="b":
            m=TARGET.match(args)
            if m and int(m[1],16) in nodes:
                queue.append((int(m[1],16),comparison,dict(constraints)))
            else:
                terminal.append({"pc":hex(pc),"constraints":constraints})
        elif pc in nxt:
            queue.append((nxt[pc],comparison,dict(constraints)))
    return {"visited_states":len(visited),"pruned_contradictions":pruned,
            "terminal_paths":terminal,
            "limitations":"Only CMP immediate with BEQ/BNE; unknown instructions drop constraints."}
