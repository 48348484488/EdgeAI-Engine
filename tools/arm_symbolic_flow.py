"""Conservative symbolic register flow over ARM disassembly branches."""
from collections import deque
import re
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location("edgeai_resolver",Path(__file__).with_name("arm_address_resolver.py"))
resolver=importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)

BRANCH=re.compile(r"^0x([0-9a-fA-F]+)")
CONDITIONAL={"beq","bne","bge","bgt","ble","blt","bhi","bls","bcc","bcs","bmi","bpl"}

def analyze(instructions):
    """Only merge matching register constants. Unrecognized operations kill knowledge."""
    if not instructions:
        return []
    indexed={int(ins["pc"],16):ins for ins in instructions}
    pcs=sorted(indexed)
    following={pc:pcs[i+1] for i,pc in enumerate(pcs[:-1])}
    entry=pcs[0]
    states={entry:{}}
    queue=deque([entry])
    while queue:
        pc=queue.popleft()
        ins=indexed[pc]
        op=ins["mnemonic"].lower()
        args=ins["operands"]
        regs=dict(states[pc])
        if op in ("movw","movt"):
            match=resolver.MOVW.match(args)
            if match:
                reg=match[1]
                imm=int(match[2],0)&0xffff
                if op=="movw": regs[reg]=imm
                elif reg in regs: regs[reg]=(regs[reg]&0xffff)|(imm<<16)
            else: regs.clear()
        elif op in ("mov","movs"):
            match=resolver.MOV.match(args)
            if match: regs[match[1]]=int(match[2],0)&0xffffffff
            else: regs.clear()
        elif op in ("add","sub"):
            match=resolver.ADD.match(args)
            if match and match[2] in regs:
                amt=int(match[3],0)
                regs[match[1]]=(regs[match[2]]+(amt if op=="add" else -amt))&0xffffffff
            else: regs.clear()
        elif op in ("cmp","cmn","tst","teq"):
            pass
        elif op.startswith("ldr"):
            match=resolver.ACCESS.match(args)
            if match: regs.pop(match[1],None)
            else: regs.clear()
        elif op.startswith("str"):
            # STR does not change registers for supported no-writeback forms.
            if resolver.ACCESS.match(args) is None: regs.clear()
        elif op in CONDITIONAL or op=="b":
            pass
        elif op in ("bx","bl","blx","pop","push"):
            regs.clear()
        else:
            regs.clear()
        if op in CONDITIONAL or op=="b":
            match=BRANCH.match(args)
            target=int(match[1],16) if match else None
            successors=[target] if op=="b" else [target,following.get(pc)]
        elif op in ("bx","bl","blx"):
            successors=[]
        else:
            successors=[following.get(pc)]
        for dst in successors:
            if dst not in indexed: continue
            if dst not in states:
                states[dst]=dict(regs)
                queue.append(dst)
            else:
                merged={key:value for key,value in states[dst].items() if regs.get(key)==value}
                if merged!=states[dst]:
                    states[dst]=merged
                    queue.append(dst)
    accesses=[]
    for pc in pcs:
        ins=indexed[pc]
        if not ins["mnemonic"].lower().startswith(("ldr","str")): continue
        state=states.get(pc)
        if state is None: continue
        match=resolver.ACCESS.match(ins["operands"])
        base=state.get(match[2]) if match else None
        address=resolver.resolve(ins["operands"],state)
        accesses.append({"pc":ins["pc"],"mnemonic":ins["mnemonic"],"operands":ins["operands"],
                         "base_address":hex(base) if base is not None else None,
                         "resolved_address":hex(address) if address is not None else None})
    return accesses
