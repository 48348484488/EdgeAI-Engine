#!/usr/bin/env python3
"""Adversarial precision/recall benchmark for EdgeAI deterministic routing."""
import argparse,hashlib,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
from hybrid_system_v015 import run_case
from router_paraphrase_v015 import cases as positive_cases

def hid(text):
    return hashlib.sha256(text.encode()).hexdigest()[:20]

def negative_cases():
    templates=[
        "Add: apples {i}",
        "Some: apples and oranges {i}",
        "What is your opinion on {i} + 47?",
        "Calculate why {i} + 47 matters",
        "What is the sum of apples and oranges {i}?",
        "Quanto vale a soma de macas e laranjas {i}?",
        "Copy exactly what I said yesterday {i}",
        "Repeat exactly what the user meant {i}",
        "Uppercase this paragraph please {i}",
        "Convert to uppercase when appropriate {i}",
        "Reverse engineering is useful {i}",
        "Reverse this idea conceptually {i}",
        "Expression for x is a phrase {i}",
        "Return only x when you explain it {i}",
        "Retorne apenas x quando explicar {i}",
        "Compute the best strategy for case {i}",
    ]
    rows=[]
    for i in range(8):
        for t in templates:
            prompt=t.format(i=i)
            rows.append(dict(id=hid(prompt),task="negative",prompt=prompt,answer=None))
    if len(rows)!=128 or len({r["prompt"] for r in rows})!=128:
        raise RuntimeError("negative corpus contract failed")
    return rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--chat",type=Path,required=True)
    p.add_argument("--out",type=Path,default=ROOT/"results/v015/router_boundary.json")
    a=p.parse_args()
    positives=positive_cases()
    negatives=negative_cases()
    if len(positives)!=128:
        raise RuntimeError("positive corpus contract failed")

    observed=[]
    for row in positives:
        r=run_case(a.chat.resolve(),row);r["expected_tool"]=True;observed.append(r)
    for row in negatives:
        r=run_case(a.chat.resolve(),row);r["expected_tool"]=False;observed.append(r)

    tp=sum(x["expected_tool"] and not x["neural_used"] for x in observed)
    fn=sum(x["expected_tool"] and x["neural_used"] for x in observed)
    fp=sum((not x["expected_tool"]) and not x["neural_used"] for x in observed)
    tn=sum((not x["expected_tool"]) and x["neural_used"] for x in observed)
    precision=tp/(tp+fp) if tp+fp else 0.0
    recall=tp/(tp+fn) if tp+fn else 0.0
    report=dict(
        protocol="balanced adversarial deterministic-router boundary benchmark",
        caveat="tests routing classification only; negative neural responses are not scored for semantic quality",
        summary=dict(count=len(observed),tool_true_positive=tp,tool_false_negative=fn,
                     tool_false_positive=fp,neural_true_negative=tn,
                     tool_precision=precision,tool_recall=recall),
        false_positives=[x for x in observed if not x["expected_tool"] and not x["neural_used"]],
        false_negatives=[x for x in observed if x["expected_tool"] and x["neural_used"]],
        cases=observed)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(report["summary"]))

if __name__=="__main__":main()
