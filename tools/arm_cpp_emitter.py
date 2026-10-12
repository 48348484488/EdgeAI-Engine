"""Small, evidence-gated C++ statement emitter for a recognized ARM function."""
def emit(analysis, read, write):
    max_pos=analysis["max_position"]
    empty=analysis["empty_value"]
    reject=analysis["rejection_value"]
    target=analysis["success_target"]
    if target!="winner":
        raise ValueError("unsupported success target")
    if not (read["board_relation"]=="board_base_dynamic_index" and write["board_relation"]=="board_base_dynamic_index"):
        raise ValueError("board base not verified")
    if read["operands"]!="r3, [r2, r0, lsl #2]":
        raise ValueError("unsupported board load")
    if write["operands"]!="r1, [r2, r0, lsl #2]":
        raise ValueError("unsupported board store")
    guards=[f"(unsigned)position > {max_pos}u",f"board[position] != {empty}"]
    statements=[f"if ({' || '.join(guards)})",
                f"    return {reject};",
                "board[position] = player;",
                f"return {target}();"]
    lines=['// ARM evidence-gated reconstruction for the recognized play pattern.',
           'extern "C" volatile int board[9];',
           'extern "C" int winner(void);',
           'extern "C" int play(int position, int player) {']
    lines+=["    "+line for line in statements]
    lines.append("}")
    return "\n".join(lines)+"\n"
