#!/usr/bin/env python3
"""Router robustness check using prompt forms absent from the v0.15 sealed range."""
import argparse,hashlib,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks'))
from hybrid_system_v015 import run_case,summarize

def hid(text):
    return hashlib.sha256(text.encode()).hexdigest()[:20]

def cases():
    rows=[]
    add_templates=(
        "Calculate {a} + {b}",
        "What is {a} + {b}?",
        "Calcule {a} + {b}",
        "Quanto e {a} + {b}?",
    )
    pairs=[(40+i%10,40+(i*7)%10) for i in range(32)]
    for i,(a,b) in enumerate(pairs):
        prompt=add_templates[i%len(add_templates)].format(a=a,b=b)
        rows.append(dict(id=hid(prompt),task="addition",prompt=prompt,answer=str(a+b)))

    strings=[
        "feceedc","fbcacdc","afcbbfc","aaadfea","deccadb","cfcfeaf","aeaadae","bcabeaf",
        "cbddcdb","ddcacfe","ccfdccf","efccdec","eaaafec","faaaeda","febcfad","badfabc",
    ]
    copy_templates=("Repeat exactly: {s}","Repita exatamente: {s}","Repeat unchanged: {s}","Repita sem alterar: {s}")
    upper_templates=("Convert to uppercase: {s}","Convert to capital letters: {s}",
                     "Converta para maiusculas: {s}","Converta para maiúsculas: {s}")
    for i in range(32):
        s=strings[i%len(strings)]
        prompt=copy_templates[i%4].format(s=s)
        rows.append(dict(id=hid(prompt),task="copy",prompt=prompt,answer=s))
    for i in range(32):
        s=strings[(i*5)%len(strings)]
        prompt=upper_templates[i%4].format(s=s)
        rows.append(dict(id=hid(prompt),task="uppercase",prompt=prompt,answer=s.upper()))

    expr_templates=(
        "Return only x {op} {k}",
        "Retorne apenas x {op} {k}",
        "Return only the Python expression x {op} {k}.",
        "Retorne apenas a expressao Python x {op} {k}.",
    )
    ops=("+","-","*")
    for i in range(32):
        k=50+(i%10);op=ops[i%3]
        prompt=expr_templates[i%4].format(op=op,k=k)
        rows.append(dict(id=hid(prompt),task="expression",prompt=prompt,answer=f"x{op}{k}"))
    return rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--chat",type=Path,required=True)
    p.add_argument("--out",type=Path,default=ROOT/"results/v015/router_paraphrases.json")
    a=p.parse_args()
    rows=cases()
    if len(rows)!=128 or len({r["prompt"] for r in rows})!=128:
        raise RuntimeError("paraphrase corpus contract failed")
    done=[run_case(a.chat.resolve(),r) for r in rows]
    by_task={t:summarize([x for x in done if x["task"]==t]) for t in sorted({x["task"] for x in done})}
    report=dict(
        protocol="deterministic router robustness on prompt forms absent from v0.15 test_range",
        caveat="tool-routing integration test; not neural intelligence or open-domain language understanding",
        summary=summarize(done),by_task=by_task,cases=done)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(dict(summary=report["summary"],by_task=by_task)))
if __name__=="__main__":main()
