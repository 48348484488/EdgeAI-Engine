"""Regression tests for conservative ARM instruction annotations."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/"tools"/"arm_semantics.py"
spec=importlib.util.spec_from_file_location("arm_semantics",path)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ARMAnnotationTests(unittest.TestCase):
    def test_mov(self):
        self.assertEqual(m.decode_arm(0xe3a00005,0x1000)["immediate"],5)
    def test_cmp(self):
        x=m.decode_arm(0xe3500009,0x1000)
        self.assertEqual((x["operation"],x["source"],x["immediate"]),("CMP","r0",9))
    def test_conditional_branch(self):
        x=m.decode_arm(0x0a000000,0x1000)
        self.assertEqual((x["condition"],x["target"]),("eq","0x1008"))
    def test_sub(self):
        x=m.decode_arm(0xe2422001,0x1000)
        self.assertEqual((x["operation"],x["source"],x["destination"],x["immediate"]),("SUB","r2","r2",1))
    def test_bx(self):
        self.assertEqual(m.decode_arm(0xe12fff1e,0x1000)["register"],"r14")
    def test_unsupported(self):
        self.assertEqual(m.decode_arm(0xe5900000,0x1000)["operation"],"unsupported")

if __name__=="__main__":
    unittest.main()
