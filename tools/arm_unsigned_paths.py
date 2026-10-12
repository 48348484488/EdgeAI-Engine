"""Unsigned ARM CMP immediate and BHI/BLS bounded path constraints."""
import re
from collections import deque
CMP=re.compile(r"^(r\d+),\s*#(0x[0-9a-fA-F]+|\d+)$")
TARGET=re.compile(r"^0x([0-9a-fA-F]+)")
def explore(ins,max_states=10000):
    nodes={int(i["pc"],16):i for i in ins}
    pcs=sorted(nodes);nxt={p:pcs[j+1] for j,p in enumerate(pcs[:-1])}
    queue=deque([(pcs[0],None,{})]) if pcs else deque()
    seen=set();term=[];forks=[];pruned=0
    while queue:
        pc,cmp,bounds=queue.popleft()
        if pc not in nodes:continue
        key=(pc,cmp,tuple(sorted(bounds.items())))
        if key in seen:continue
        seen.add(key)
        if len(seen)>max_states:raise ValueError("state budget exceeded")
        op=nodes[pc]["mnemonic"].lower();args=nodes[pc]["operands"]
        if op=="cmp":
            m=CMP.fullmatch(args.strip())
            cmp=(m[1],int(m[2],0)) if m else None
        elif op in ("bhi","bls"):
            m=TARGET.match(args)
            if m:
                for taken,dest in ((True,int(m[1],16)),(False,nxt.get(pc))):
                    if dest is None:continue
                    state=dict(bounds)
                    if cmp:
                        reg,value=cmp;lo,hi=state.get(reg,(0,0xffffffff))
                        greater=(op=="bhi")==taken
                        if greater:lo=max(lo,value+1)
                        else:hi=min(hi,value)
                        if lo>hi:pruned+=1;continue
                        state[reg]=(lo,hi)
                    queue.append((dest,cmp,state))
                    forks.append({"branch_pc":hex(pc),"taken":taken,"destination":hex(dest),"bounds":state})
                continue
        elif op in ("beq","bne","bge","blt","bgt","ble","bcs","bcc","bmi","bpl"):
            m=TARGET.match(args)
            if m and int(m[1],16) in nodes:queue.append((int(m[1],16),None,dict(bounds)))
            if pc in nxt:queue.append((nxt[pc],None,dict(bounds)))
            continue
        elif op in ("bx","pop"):
            term.append({"pc":hex(pc),"unsigned_bounds":bounds});continue
        elif op in ("ldr","ldrb","mov","movw","movt","add","sub"):
            dst=args.split(",",1)[0].strip()
            bounds={r:v for r,v in bounds.items() if r!=dst};cmp=None
        elif op not in ("b","str","cmp","bhi","bls"):
            bounds={};cmp=None
        if op=="b":
            m=TARGET.match(args)
            if m:
                dest=int(m[1],16)
                if dest in nodes:queue.append((dest,cmp,dict(bounds)))
                else:term.append({"pc":hex(pc),"unsigned_bounds":bounds})
        elif pc in nxt:queue.append((nxt[pc],cmp,dict(bounds)))
    return {"visited_states":len(seen),"pruned_contradictions":pruned,
            "terminal_paths":term,"branch_constraints":forks,
            "scope":"CMP immediate, BHI/BLS, unsigned 32-bit; conservative partial"}
