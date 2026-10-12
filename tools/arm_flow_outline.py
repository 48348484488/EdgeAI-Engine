#!/usr/bin/env python3
"""Relatório conservador de fluxo e saltos entre entradas conhecidas de ARM32."""
import argparse
import importlib.util
import json
from pathlib import Path

spec=importlib.util.spec_from_file_location("edgeai_arm_cfg",Path(__file__).with_name("arm_cfg.py"))
cfg=importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)

def analyze(data, entries, mode="arm"):
    entries=set(entries)
    if not entries:
        raise cfg.arm.ScanError("at least one known function entry is required")
    results=[]
    for start in sorted(entries):
        graph=cfg.build(data,start,mode)
        external=[]
        for edge in graph["edges"]:
            if edge["type"]!="taken":
                continue
            source,target=int(edge["from"],16),int(edge["to"],16)
            if target in entries and target!=start:
                external.append({"site":hex(source),"target":hex(target),
                                 "classification":"possible_tail_transfer"})
        lines=[f"função_candidata_{start:x}() {{",
               f"    // {graph['instruction_count']} instruções alcançadas"]
        for edge in external:
            lines.append(f"    // possível salto para função em {edge['target']} (origem {edge['site']})")
        lines.extend(["    // comportamento não reconstruído", "}"])
        results.append({"entry":hex(start),"instructions":graph["instruction_count"],
                        "possible_tail_transfers":external,
                        "pseudocode_outline":"\n".join(lines)})
    return {"mode":mode,"functions":results,"warning":
            "Only direct unconditional branches to independently known entries are classified. "
            "This is an outline, not inferred semantics or C++ reconstruction."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("elf",type=Path)
    p.add_argument("--entry",action="append",required=True,type=lambda v:int(v,0))
    p.add_argument("--mode",choices=["arm","thumb"],default="arm")
    a=p.parse_args()
    try:
        if a.elf.stat().st_size>128*1024*1024:
            raise cfg.arm.ScanError("ELF exceeds 128 MiB")
        report=analyze(a.elf.read_bytes(),a.entry,a.mode)
    except (OSError,cfg.arm.ScanError) as exc:
        p.exit(2,f"error: {exc}\n")
    print(json.dumps(report,indent=2,ensure_ascii=False))
if __name__=="__main__":
    main()
