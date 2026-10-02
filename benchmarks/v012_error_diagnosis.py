#!/usr/bin/env python3
"""Diagnose where v0.12 one-block and two-block native generation diverge."""
import argparse,json
from collections import defaultdict
from pathlib import Path

def pct(n,d): return 100.0*n/d if d else 0.0

def analyze(report):
    examples=report.get("examples",[])
    if not examples: raise ValueError("evaluation report has no per-example evidence")
    grouped=defaultdict(lambda: defaultdict(lambda: {"count":0,"correct":0,"exact":0}))
    for r in examples:
        key=(int(r["seed"]),int(r["blocks"]))
        for axis in ("split","task","language"):
            name=str(r[axis])
            x=grouped[axis][(key,name)]
            x["count"]+=1;x["correct"]+=int(bool(r["correct"]));x["exact"]+=int(bool(r["exact"]))
    comparisons={}
    for axis,rows in grouped.items():
        names=sorted({name for (_,name) in rows})
        axis_out={}
        for name in names:
            seeds=sorted({seed for ((seed,_),n) in rows if n==name})
            pairs=[]
            for seed in seeds:
                a=rows.get(((seed,1),name));b=rows.get(((seed,2),name))
                if not a or not b: continue
                pairs.append({"seed":seed,"count":a["count"],
                    "b1_correct":a["correct"],"b2_correct":b["correct"],
                    "delta_correct":b["correct"]-a["correct"],
                    "b1_exact":a["exact"],"b2_exact":b["exact"],
                    "delta_exact":b["exact"]-a["exact"]})
            axis_out[name]={"pairs":pairs,
                "delta_correct_total":sum(p["delta_correct"] for p in pairs),
                "delta_exact_total":sum(p["delta_exact"] for p in pairs),
                "b2_seed_wins_correct":sum(p["delta_correct"]>0 for p in pairs),
                "b1_seed_wins_correct":sum(p["delta_correct"]<0 for p in pairs)}
        comparisons[axis]=axis_out
    total1=sum(bool(r["correct"]) for r in examples if r["blocks"]==1)
    total2=sum(bool(r["correct"]) for r in examples if r["blocks"]==2)
    return {"protocol":"post-hoc diagnostic over frozen v0.12 native-generation evidence; no retraining",
        "rows":len(examples),"correct":{"blocks1":total1,"blocks2":total2,"delta_blocks2_minus_blocks1":total2-total1},
        "comparisons":comparisons}

def main():
    p=argparse.ArgumentParser();p.add_argument("--evaluation",type=Path,default=Path("results/v012/evaluation.json"));p.add_argument("--out",type=Path,default=Path("results/v012/error_diagnosis.json"));a=p.parse_args()
    report=json.loads(a.evaluation.read_text(encoding="utf-8"));out=analyze(report);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"correct":out["correct"],"out":str(a.out)}))
if __name__=="__main__": main()
