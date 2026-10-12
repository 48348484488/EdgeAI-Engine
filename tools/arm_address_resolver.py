#!/usr/bin/env python3
"""Resolve demonstrable ARM memory addresses, including register-offset modes."""
import re

ACCESS=re.compile(r"^(r\d+),\s*\[(r\d+)(?:,\s*(#[+-]?\d+|r\d+)(?:,\s*lsl\s*#(\d+))?)?\]$")
MOV=re.compile(r"^(r\d+),\s*#([+-]?(?:0x[0-9a-fA-F]+|\d+))$")
ADD=re.compile(r"^(r\d+),\s*(r\d+),\s*#([+-]?(?:0x[0-9a-fA-F]+|\d+))$")
MOVW=re.compile(r"^(r\d+),\s*#(0x[0-9a-fA-F]+|\d+)$")

def resolve(operands, registers):
    match=ACCESS.match(operands.strip())
    if match is None:
        return None
    dest,base,index,shift=match.groups()
    if base not in registers:
        return None
    delta=0
    if index:
        if index.startswith("#"):
            delta=int(index[1:],0)
        else:
            if index not in registers:
                return None
            delta=registers[index] << int(shift or 0)
    return (registers[base]+delta)&0xffffffff

def walk(instructions, initial=None):
    """Straight-line only. A barrier clears knowledge; never follows branches."""
    registers=dict(initial or {})
    accesses=[]
    for ins in instructions:
        op=ins["mnemonic"].lower()
        args=ins["operands"]
        if op in ("movw","movt"):
            match=MOVW.match(args)
            if not match:
                registers.clear()
            elif op=="movw":
                registers[match[1]]=int(match[2],0)&0xffff
            elif match[1] in registers:
                registers[match[1]]=(registers[match[1]]&0xffff)|((int(match[2],0)&0xffff)<<16)
        elif op in ("cmp","cmn","tst","teq"):
            # Comparisons affect flags but do not modify general registers.
            pass
        elif op in ("mov","movs"):
            match=MOV.match(args)
            if match: registers[match[1]]=int(match[2],0)&0xffffffff
            else: registers.clear()
        elif op in ("add","sub"):
            match=ADD.match(args)
            if match and match[2] in registers:
                amount=int(match[3],0)
                registers[match[1]]=(registers[match[2]]+(amount if op=="add" else -amount))&0xffffffff
            else: registers.clear()
        elif op.startswith(("ldr","str")):
            address=resolve(args,registers)
            match=ACCESS.match(args)
            base=registers.get(match[2]) if match else None
            accesses.append({"pc":ins["pc"],"mnemonic":op,"operands":args,
                             "base_address":hex(base) if base is not None else None,
                             "resolved_address":hex(address) if address is not None else None})
            if op.startswith("ldr"):
                match=ACCESS.match(args)
                if match: registers.pop(match[1],None)
                else: registers.clear()
        elif op in ("b","bx","bl","blx") or op.startswith(("b.","pop","push")):
            registers.clear()
        else:
            registers.clear()
    return accesses
