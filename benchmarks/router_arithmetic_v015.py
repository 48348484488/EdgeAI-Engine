#!/usr/bin/env python3
"""Batch benchmark for natural-language deterministic arithmetic routing."""
import argparse,hashlib,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
from hybrid_system_v015 import run_case,summarize

def hid(text):
    return hashlib.sha256(text.encode()).hexdigest()[:20]

def cases():
    rows=[]
    for i in range(16):
        a=40+i;b=3+(i%9)
        for prompt,answer in (
            (f"Subtract {b} from {a}",str(a-b)),
            (f"Subtraia {b} de {a}",str(a-b)),
        ):
            rows.append(dict(id=hid(prompt),task="subtract",prompt=prompt,answer=answer))
    for i in range(16):
        a=2+i;b=3+(i%7)
        for prompt,answer in (
            (f"Multiply {a} by {b}",str(a*b)),
            (f"Multiplique {a} por {b}",str(a*b)),
        ):
            rows.append(dict(id=hid(prompt),task="multiply",prompt=prompt,answer=answer))
    for i in range(16):
        divisor=2+(i%8);quotient=3+i;value=divisor*quotient
        for prompt,answer in (
            (f"Divide {value} by {divisor}",str(quotient)),
            (f"Divida {value} por {divisor}",str(quotient)),
        ):
            rows.append(dict(id=hid(prompt),task="divide",prompt=prompt,answer=answer))
    if len(rows)!=96 or len({r["prompt"] for r in rows})!=96:
        raise RuntimeError("arithmetic corpus contract failed")
    return rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--chat",type=Path,required=True)
    p.add_argument("--out",type=Path,default=ROOT/"results/v015/router_arithmetic.json")
    a=p.parse_args()
    done=[run_case(a.chat.resolve(),r) for r in cases()]
    by_task={t:summarize([x for x in done if x["task"]==t]) for t in sorted({x["task"] for x in done})}
    report=dict(
        protocol="natural-language bilingual deterministic arithmetic routing",
        caveat="system/tool benchmark; not neural arithmetic generalization",
        summary=summarize(done),by_task=by_task,cases=done)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(dict(summary=report["summary"],by_task=by_task)))

if __name__=="__main__":main()
