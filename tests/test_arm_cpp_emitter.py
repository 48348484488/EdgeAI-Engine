import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/"tools"/"arm_cpp_emitter.py"
spec=importlib.util.spec_from_file_location("cpp_emitter",p)
e=importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)

def access(op,operands):
    return {"board_relation":"board_base_dynamic_index","operands":operands}

class TestEmitter(unittest.TestCase):
    def test_emits_guard_write_and_call(self):
        rules={"max_position":8,"empty_value":0,"rejection_value":-1,"success_target":"winner"}
        cpp=e.emit(rules,access("ldr","r3, [r2, r0, lsl #2]"),access("str","r1, [r2, r0, lsl #2]"))
        self.assertIn("(unsigned)position > 8u",cpp)
        self.assertIn("board[position] = player;",cpp)
        self.assertIn("return winner();",cpp)
    def test_rejects_unknown_store(self):
        rules={"max_position":8,"empty_value":0,"rejection_value":-1,"success_target":"winner"}
        with self.assertRaises(ValueError):
            e.emit(rules,access("ldr","r3, [r2, r0, lsl #2]"),access("str","r4, [r2, r0, lsl #2]"))
if __name__=="__main__":unittest.main()
