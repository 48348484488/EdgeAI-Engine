"""Build a bounded control-flow IR from existing ARM ELF analysis."""
import importlib.util
from pathlib import Path

def load(name):
    p=Path(__file__).with_name(name+".py")
    spec=importlib.util.spec_from_file_location("edge_"+name,p)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
semantics=load("arm_semantics")

def from_analysis(analysis):
    if analysis.get("mode")!="arm":
        raise ValueError("Only ARM32 mode is supported")
    nodes=[]
    for ins in analysis["annotations"]:
        pc=ins["address"]
        op=ins["operation"]
        condition=ins["condition"]
        item={"address":pc,"condition":condition}
        if op=="MOV" and condition=="al":
            item.update(op="constant",destination=ins["destination"],value=ins["immediate"])
        elif op in ("ADD","SUB") and condition=="al":
            item.update(op="binary",destination=ins["destination"],
                        kind=op.lower(),lhs=ins["source"],rhs=ins["immediate"])
        elif op=="CMP" and condition=="al":
            item.update(op="compare",lhs=ins["source"],rhs=ins["immediate"])
        elif op in ("B","BL"):
            item.update(op="branch" if op=="B" else "call",target=ins["target"])
        elif op=="BX" and condition=="al":
            item.update(op="indirect_branch",register=ins["register"])
        else:
            item.update(op="unsupported",reason="conditional_or_unknown")
        nodes.append(item)
    return {"architecture":"ARM32","entry":analysis["entry"],
            "nodes":nodes,"edges":list(analysis["edges"]),
            "unsupported_count":sum(x["op"]=="unsupported" for x in nodes),
            "note":"Control-flow representation only; no generic C++ structuring proof"}

def from_elf(data,entry,max_instructions=1024):
    return from_analysis(semantics.analyze(data,entry,max_instructions))
