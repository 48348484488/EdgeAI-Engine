"""Extract conservative branch forks from real LLVM ARM disassembly."""
import re
BRANCHES={"beq","bne","bhi","bls","bge","blt","bgt","ble","bcs","bcc","bmi","bpl"}
TARGET=re.compile(r"^(0x[0-9a-fA-F]+)")
def analyze(instructions):
    pcs={int(x["pc"],16) for x in instructions}
    forks=[]
    for i,ins in enumerate(instructions):
        op=ins["mnemonic"].lower()
        if op not in BRANCHES: continue
        match=TARGET.match(ins["operands"])
        if not match: continue
        target=int(match[1],16)
        fallthrough=int(instructions[i+1]["pc"],16) if i+1<len(instructions) else None
        if target not in pcs or fallthrough not in pcs: continue
        forks.append({"branch_pc":ins["pc"],"condition":op[1:],
                      "taken":hex(target),"fallthrough":hex(fallthrough)})
    return {"function_branch_forks":forks,
            "fork_count":len(forks),
            "scope":"Direct conditional branches with both endpoints inside disassembled function"}
