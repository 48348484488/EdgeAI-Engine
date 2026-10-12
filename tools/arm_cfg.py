#!/usr/bin/env python3
"""Bounded, conservative CFG of explicitly selected ARM32/Thumb16 entry points."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

spec=importlib.util.spec_from_file_location("edgeai_arm_scan",Path(__file__).with_name("arm_scan.py"))
arm=importlib.util.module_from_spec(spec)
spec.loader.exec_module(arm)

def build(data,entry,mode,max_instructions=4096):
    if mode not in ("arm","thumb") or not 1<=max_instructions<=100000:
        raise arm.ScanError("invalid mode or instruction budget")
    order,segments=arm.exec_segments(data)
    step=4 if mode=="arm" else 2
    if entry%step: raise arm.ScanError("unaligned entry")
    def locate(pc):
        for off,base,size in segments:
            if base<=pc and pc+step<=base+size and (pc-base)%step==0:
                return off+pc-base
        return None
    if locate(entry) is None: raise arm.ScanError("entry outside executable segment")
    nodes,edges,unresolved={},set(),set()
    queue=[entry]
    while queue:
        pc=queue.pop()
        if pc in nodes: continue
        if len(nodes)>=max_instructions: raise arm.ScanError("instruction budget exceeded")
        off=locate(pc)
        if off is None:
            unresolved.add(pc)
            continue
        op=struct.unpack(order+("I" if mode=="arm" else "H"),data[off:off+step])[0]
        kind,target,conditional="other",None,False
        if mode=="arm":
            cond=(op>>28)&15
            if cond!=15 and ((op>>25)&7)==5:
                target=(pc+8+(arm.signext(op&0xffffff,24)<<2))&0xffffffff
                kind="BL" if op&(1<<24) else "B"
                conditional=cond!=14
            elif op&0x0ffffff0==0x012fff10:
                kind="indirect"
            elif op&0x0ffffff0==0x012fff30:
                kind="indirect-call"
        else:
            if op&0xf800 in (0xe800,0xf000,0xf800):
                kind="unsupported-thumb32"
            elif op&0xf800==0xe000:
                kind="B"
                target=(pc+4+(arm.signext(op&0x7ff,11)<<1))&0xffffffff
            elif op&0xf000==0xd000 and (op>>8)&15<14:
                kind="B.cond"
                conditional=True
                target=(pc+4+(arm.signext(op&0xff,8)<<1))&0xffffffff
            elif op&0xff87==0x4700:
                kind="indirect"
            elif op&0xff87==0x4780:
                kind="indirect-call"
            elif op&0xff00==0xbd00:
                kind="unknown-control"
        nodes[pc]={"address":hex(pc),"kind":kind,"width":step}
        successors=[]
        if kind in ("B","B.cond"):
            successors.append((target,"taken"))
            if conditional: successors.append((pc+step,"fallthrough"))
        elif kind=="BL":
            edges.add((pc,target,"call"))
            successors.append((pc+step,"fallthrough"))
        elif kind in ("other","indirect-call"):
            successors.append((pc+step,"fallthrough"))
        for nxt,label in successors:
            edges.add((pc,nxt,label))
            if nxt not in nodes: queue.append(nxt)
    return {"architecture":"ARM32","mode":mode,"entry":hex(entry),
            "instruction_count":len(nodes),
            "instructions":[nodes[k] for k in sorted(nodes)],
            "edges":[{"from":hex(a),"to":hex(b),"type":t} for a,b,t in sorted(edges)],
            "unresolved_targets":[hex(k) for k in sorted(unresolved)],
            "limitations":"Partial decoder; explicit ISA and entry; no automatic function recovery."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("file",type=Path)
    p.add_argument("--entry",type=lambda x:int(x,0),required=True)
    p.add_argument("--mode",choices=("arm","thumb"),required=True)
    p.add_argument("--max-instructions",type=int,default=4096)
    a=p.parse_args()
    try:
        if a.file.stat().st_size>128*1024*1024: raise arm.ScanError("file too large")
        result=build(a.file.read_bytes(),a.entry,a.mode,a.max_instructions)
    except (OSError,arm.ScanError,struct.error) as e:
        p.exit(2,f"error: {e}\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
