"""Minimal typed intermediate representation for evidence-backed play reconstruction."""
def lower(rules,read,write):
    if rules.get("success_target")!="winner": raise ValueError("unknown callee")
    if read.get("board_relation")!="board_base_dynamic_index" or write.get("board_relation")!="board_base_dynamic_index":
        raise ValueError("unverified board reference")
    if read.get("operands")!="r3, [r2, r0, lsl #2]" or write.get("operands")!="r1, [r2, r0, lsl #2]":
        raise ValueError("unsupported indexed load/store")
    return [
        {"op":"guard_gt_unsigned","argument":"r0","limit":int(rules["max_position"]),"reject":int(rules["rejection_value"])},
        {"op":"guard_not_equal","array":"board","index":"r0","value":int(rules["empty_value"]),"reject":int(rules["rejection_value"])},
        {"op":"store_indexed","array":"board","index":"r0","source":"r1","stride":4},
        {"op":"tail_call","target":rules["success_target"]}
    ]

def emit_cpp(ir):
    header=['// Generated from supported EdgeAI IR, not recovered original source.',
            'extern "C" volatile int board[9];',
            'extern "C" int winner(void);',
            'extern "C" int play(int position, int player) {']
    reg={"r0":"position","r1":"player"}
    body=[]
    for node in ir:
        op=node["op"]
        if op=="guard_gt_unsigned":
            body.append(f'if ((unsigned){reg[node["argument"]]} > {node["limit"]}u) return {node["reject"]};')
        elif op=="guard_not_equal":
            body.append(f'if ({node["array"]}[{reg[node["index"]]}] != {node["value"]}) return {node["reject"]};')
        elif op=="store_indexed":
            if node["stride"]!=4: raise ValueError("unsupported element size")
            body.append(f'{node["array"]}[{reg[node["index"]]}] = {reg[node["source"]]};')
        elif op=="tail_call":
            if node["target"]!="winner": raise ValueError("unresolved callee")
            body.append("return winner();")
        else: raise ValueError("unsupported IR operation")
    return "\n".join(header+["    "+line for line in body]+["}",""])

def emit_expression(node, names=None):
    """Small reusable C++ expression backend for non-game-specific IR."""
    names=names or {}
    def operand(value):
        if isinstance(value,int):
            return str(value)
        if isinstance(value,str) and value in names:
            return names[value]
        raise ValueError("unmapped IR operand")
    op=node.get("op")
    if op=="constant":
        return operand(node["value"])
    if op=="binary":
        operators={"add":"+","sub":"-","eq":"==","ult":"<"}
        kind=node.get("kind")
        if kind not in operators:
            raise ValueError("unsupported binary IR operator")
        return "("+operand(node["lhs"])+" "+operators[kind]+" "+operand(node["rhs"])+")"
    if op=="move":
        return operand(node["source"])
    raise ValueError("unsupported expression IR node")
