import importlib.util
from pathlib import Path
import unittest
p=Path(__file__).resolve().parents[1]/"tools"/"arm_ir.py"
s=importlib.util.spec_from_file_location("arm_ir",p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class IRTests(unittest.TestCase):
    def test_lower_and_emit(self):
        rules={"max_position":8,"empty_value":0,"rejection_value":-1,"success_target":"winner"}
        read={"board_relation":"board_base_dynamic_index","operands":"r3, [r2, r0, lsl #2]"}
        write={"board_relation":"board_base_dynamic_index","operands":"r1, [r2, r0, lsl #2]"}
        ir=m.lower(rules,read,write)
        self.assertEqual([n["op"] for n in ir],["guard_gt_unsigned","guard_not_equal","store_indexed","tail_call"])
        cpp=m.emit_cpp(ir)
        self.assertIn("board[position] = player;",cpp)
    def test_unknown_memory_pattern_rejected(self):
        rules={"max_position":8,"empty_value":0,"rejection_value":-1,"success_target":"winner"}
        read={"board_relation":"board_base_dynamic_index","operands":"r3, [r2, r0, lsl #2]"}
        write={"board_relation":"board_base_dynamic_index","operands":"r5, [r2, r0, lsl #2]"}
        with self.assertRaises(ValueError): m.lower(rules,read,write)
if __name__=="__main__":unittest.main()
