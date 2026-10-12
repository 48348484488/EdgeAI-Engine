"""Conservative ARM immediate instruction to generic IR translation."""
import importlib.util
from pathlib import Path

path=Path(__file__).with_name("arm_semantics.py")
spec=importlib.util.spec_from_file_location("semantics",path)
sem=importlib.util.module_from_spec(spec)
spec.loader.exec_module(sem)

def lift(word,pc):
    instruction=sem.decode_arm(word,pc)
    op=instruction["operation"]
    condition=instruction["condition"]
    if condition!="al":
        return {"op":"unsupported","address":hex(pc),"reason":"conditional_instruction"}
    if op=="MOV":
        return {"op":"constant","address":hex(pc),"destination":instruction["destination"],
                "value":instruction["immediate"]}
    if op in ("ADD","SUB"):
        return {"op":"binary","address":hex(pc),"destination":instruction["destination"],
                "kind":op.lower(),"lhs":instruction["source"],"rhs":instruction["immediate"]}
    if op=="CMP":
        return {"op":"compare","address":hex(pc),"lhs":instruction["source"],
                "rhs":instruction["immediate"],"sets_flags":True}
    if op in ("B","BL"):
        return {"op":"branch" if op=="B" else "call","address":hex(pc),
                "target":instruction["target"]}
    if op=="BX":
        return {"op":"indirect_branch","address":hex(pc)}
    return {"op":"unsupported","address":hex(pc),"reason":"unrecognized_instruction"}
