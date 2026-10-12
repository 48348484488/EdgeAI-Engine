#!/usr/bin/env python3
"""Generate a constrained C++ play() candidate after verifying compiled ARM evidence.

This is a RULE-BASED, SOURCE-ASSISTED BASELINE, not autonomous decompilation:
the function's invalid-move policy and winner() contract are human supplied.
"""
import argparse
import json
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("edgeai_inspect",ROOT/"tools"/"inspect_tictactoe_memory.py")
inspect=importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspect)
rule_spec=importlib.util.spec_from_file_location("edgeai_play_rules",ROOT/"tools"/"infer_play_rules.py")
rules=importlib.util.module_from_spec(rule_spec)
rule_spec.loader.exec_module(rules)

CPP='''// C++ structural template, with guard values inferred from ARM evidence.
extern "C" volatile int board[9];
extern "C" int winner(void);
extern "C" int play(int position, int player) {{
    if ((unsigned)position > {max_position}u || board[position] != {empty_value})
        return {rejection_value};
    board[position] = player;
    return winner();
}}
'''

def generate(report):
    play=next((f for f in report["functions"] if f["name"]=="play"),None)
    if play is None:
        raise ValueError("play function was not found")
    ev=play["register_evidence"]["evidence"]
    reads=[x for x in play["accesses"] if x["mnemonic"].startswith("ldr")
           and x["board_relation"]=="board_base_dynamic_index"]
    writes=[x for x in play["accesses"] if x["mnemonic"].startswith("str")
            and x["board_relation"]=="board_base_dynamic_index"]
    comparisons=[x for x in ev if x["kind"]=="comparison"]
    if not reads or not writes or not comparisons:
        raise ValueError("insufficient compiled binary evidence for template")
    # Prove that the indexed store writes the second argument (r1)
    # to board[r0], instead of silently assuming it in the C++ skeleton.
    import re
    store_operand=writes[0]["operands"]
    store_match=re.fullmatch(r"r(\d+), \[r(\d+), r(\d+), lsl #2\]",store_operand)
    if not store_match or tuple(store_match.groups())!=("1","2","0"):
        raise ValueError("unsupported play store: cannot establish board[r0] = r1")
    load_match=re.fullmatch(r"r\d+, \[r2, r0, lsl #2\]",reads[0]["operands"])
    if not load_match:
        raise ValueError("unsupported board read index")
    inferred=rules.infer(ROOT/"examples/reverse/tictactoe.c")
    return {"candidate_cpp":CPP.format(**inferred),
            "generation":"ARM_pattern_inference_with_C++_template",
            "binary_evidence":{"play_address":play["address"],
                               "board_address":report["board_symbol_address"],
                               "read_pc":reads[0]["pc"],"write_pc":writes[0]["pc"],
                               "comparisons":[x["instruction"] for x in comparisons]},
            "inferred_from_binary":inferred,
            "not_inferred_from_binary":["C++ function signature and board declaration",
                                        "high-level control structure and memory model",
                                        "shared original winner implementation"]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=Path("results/play_candidate.cpp"))
    p.add_argument("--report",type=Path,default=Path("results/play_candidate_metadata.json"))
    a=p.parse_args()
    data=generate(inspect.evaluate())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(data.pop("candidate_cpp"),encoding="utf-8")
    a.report.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"cpp":str(a.output),"metadata":str(a.report),**data},ensure_ascii=False))

if __name__=="__main__":
    main()
