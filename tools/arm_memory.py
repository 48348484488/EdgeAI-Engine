#!/usr/bin/env python3
"""Rastreia acessos ARM32 LDR/STR imediatos em um bloco linear, sem executar binarios."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

spec=importlib.util.spec_from_file_location("edgeai_sem",Path(__file__).with_name("arm_semantics.py"))
sem=importlib.util.module_from_spec(spec)
spec.loader.exec_module(sem)

def decode_memory(word):
    # Single data transfer: immediate offset, word, pre-indexed, no writeback.
    if ((word>>26)&3)!=1 or word&(1<<25) or word&(1<<22) or not word&(1<<24) or word&(1<<21):
        return None
    rn=(word>>16)&15
    rd=(word>>12)&15
    if rn==15 or rd==15:
        return None
    return {"operation":"LDR" if word&(1<<20) else "STR",
            "base":f"r{rn}","register":f"r{rd}",
            "offset":(word&4095)*(1 if word&(1<<23) else -1)}

def analyze(data,entry,max_steps=256):
    if entry%4 or not 1<=max_steps<=4096:
        raise sem.cfg.arm.ScanError("invalid ARM entry or step count")
    order,segs=sem.cfg.arm.exec_segments(data)
    regs={}
    memory={}
    accesses=[]
    pc=entry
    stopped="outside executable segment"
    for _ in range(max_steps):
        offset=next((off+pc-base for off,base,size in segs if base<=pc and pc+4<=base+size),None)
        if offset is None: break
        word=struct.unpack_from(order+"I",data,offset)[0]
        cond=(word>>28)&15
        if cond!=14:
            stopped="conditional instruction"
            break
        access=decode_memory(word)
        if access is not None:
            base=regs.get(access["base"])
            address=None if base is None else (base+access["offset"])&0xffffffff
            reg=access["register"]
            if access["operation"]=="STR":
                if address is None:
                    memory.clear()
                else:
                    value=regs.get(reg)
                    if value is None: memory.pop(address,None)
                    else: memory[address]=value
            else:
                value=memory.get(address) if address is not None else None
                if value is None: regs.pop(reg,None)
                else: regs[reg]=value
            accesses.append({"pc":hex(pc),"operation":access["operation"],
                "address":hex(address) if address is not None else None,
                "value":hex(regs[reg]) if access["operation"]=="LDR" and reg in regs else
                       (hex(memory[address]) if address is not None and address in memory and access["operation"]=="STR" else None)})
        else:
            decoded=sem.decode_arm(word,pc)
            op=decoded["operation"]
            if op=="MOV":
                regs[decoded["destination"]]=decoded["immediate"]
            elif op in ("ADD","SUB"):
                v=regs.get(decoded["source"])
                dst=decoded["destination"]
                if v is None: regs.pop(dst,None)
                else: regs[dst]=(v+decoded["immediate"] if op=="ADD" else v-decoded["immediate"])&0xffffffff
            elif op=="CMP":
                pass
            else:
                stopped="unsupported or control-transfer instruction"
                break
        pc+=4
    return {"entry":hex(entry),"memory_accesses":accesses,
            "known_registers":{k:hex(v) for k,v in sorted(regs.items())},
            "known_writes":{hex(k):hex(v) for k,v in sorted(memory.items())},
            "stopped_reason":stopped,
            "limitations":"Only ARM unconditional word LDR/STR immediate pre-indexed without writeback. Memory begins unknown; unknown stores invalidate tracked memory. No pointer alias analysis, memory mapping, branches or execution."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path)
    p.add_argument("--entry",required=True,type=lambda v:int(v,0))
    a=p.parse_args()
    try:
        if a.elf.stat().st_size>128*1024*1024:
            raise sem.cfg.arm.ScanError("file too large")
        out=analyze(a.elf.read_bytes(),a.entry)
    except (OSError,sem.cfg.arm.ScanError,struct.error) as e:
        p.exit(2,f"error: {e}\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
