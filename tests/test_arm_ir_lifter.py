import importlib.util
from pathlib import Path
import unittest
p=Path(__file__).resolve().parents[1]/"tools"/"arm_ir_lifter.py"
spec=importlib.util.spec_from_file_location("arm_ir_lifter",p)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
class Tests(unittest.TestCase):
    def test_immediate_mov(self):
        out=module.lift(0xe3a00005,0x1000)
        self.assertEqual((out["op"],out["destination"],out["value"]),("constant","r0",5))
    def test_immediate_add(self):
        out=module.lift(0xe2801003,0x1004)
        self.assertEqual((out["op"],out["kind"],out["lhs"],out["rhs"]),("binary","add","r0",3))
    def test_cmp(self):
        out=module.lift(0xe3500008,0x1008)
        self.assertEqual((out["op"],out["rhs"]),("compare",8))
    def test_unknown_conditional(self):
        self.assertEqual(module.lift(0x03a00005,0x1000)["op"],"unsupported")
if __name__=="__main__":unittest.main()
