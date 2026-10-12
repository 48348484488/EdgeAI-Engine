#!/usr/bin/env python3
"""Anotacao conservadora de instrucoes ARM32; ainda nao e descompilador."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

spec=importlib.util.spec_from_file_location("edgeai_cfg",Path(__file__).with_name("arm_cfg.py"))
cfg=importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)
CONDITIONS=("eq","ne","cs","cc","mi","pl","vs","vc","hi","ls","ge","lt","gt","le","al","reserved")

def rotate_right(x,n):
    n%=32
    return ((x>>n)|(x<<(32-n)))&0xffffffff if n else x

def decode_arm(word,pc):
    condition=(word>>28)&15
    result={"address":hex(pc),"encoding":f"{word:08x}","condition":CONDITIONS[condition]}
    if condition==15:
        result["operation"]="unsupported"
    elif (word>>25)&7==5:
        offset=(word&0xffffff)<<2
        if offset&(1<<25): offset-=1<<26
        result.update(operation="BL" if word&(1<<24) else "B",
                      target=hex((pc+8+offset)&0xffffffff))
    elif word&0x0ffffff0==0x012fff10:
        result.update(operation="BX",register="r"+str(word&15))
    elif (word>>25)&7==1 and ((word>>21)&15) in (2,4,10,13):
        opcode=(word>>21)&15
        name={2:"SUB",4:"ADD",10:"CMP",13:"MOV"}[opcode]
        immediate=rotate_right(word&255,((word>>8)&15)*2)
        result.update(operation=name,immediate=immediate)
        if name!="MOV": result["source"]="r"+str((word>>16)&15)
        if name!="CMP": result["destination"]="r"+str((word>>12)&15)
        if name!="CMP": result["sets_flags"]=bool(word&(1<<20))
    else:
        result["operation"]="unsupported"
    return result

def analyze(data,entry,max_instructions=4096):
    graph=cfg.build(data,entry,"arm",max_instructions)
    order,segments=cfg.arm.exec_segments(data)
    annotations=[]
    for node in graph["instructions"]:
        pc=int(node["address"],16)
        for off,base,size in segments:
            if base<=pc and pc+4<=base+size:
                word=struct.unpack(order+"I",data[off+pc-base:off+pc-base+4])[0]
                annotations.append(decode_arm(word,pc))
                break
    return {"entry":hex(entry),"mode":"arm","annotations":annotations,
            "edges":graph["edges"],
            "limitations":"Partial ARM-state decoding, no register value propagation, type inference or semantics reconstruction."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path)
    p.add_argument("--entry",type=lambda s:int(s,0),required=True)
    a=p.parse_args()
    try:
        if a.elf.stat().st_size>128*1024*1024:
            raise cfg.arm.ScanError("file exceeds 128 MiB")
        result=analyze(a.elf.read_bytes(),a.entry)
    except (OSError,cfg.arm.ScanError,struct.error) as e:
        p.exit(2,f"error: {e}\n")
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
