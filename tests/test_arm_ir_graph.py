import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/"tools"/"arm_ir_graph.py"
spec=importlib.util.spec_from_file_location("graph_ir",p)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class GraphIRTests(unittest.TestCase):
    def test_conditional_branch_preserves_edges(self):
        data={"mode":"arm","entry":"0x1000","annotations":[
            {"address":"0x1000","operation":"CMP","condition":"al","source":"r0","immediate":8},
            {"address":"0x1004","operation":"B","condition":"hi","target":"0x1010"},
            {"address":"0x1008","operation":"MOV","condition":"al","destination":"r1","immediate":5},
            {"address":"0x100c","operation":"BX","condition":"al","register":"r14"}],
            "edges":[{"from":"0x1004","to":"0x1010","type":"taken"},
                     {"from":"0x1004","to":"0x1008","type":"fallthrough"}]}
        g=module.from_analysis(data)
        self.assertEqual([x["op"] for x in g["nodes"]],["compare","branch","constant","indirect_branch"])
        self.assertEqual(g["nodes"][1]["condition"],"hi")
        self.assertEqual(len(g["edges"]),2)
        self.assertEqual(g["unsupported_count"],0)
    def test_unknown_is_visible(self):
        g=module.from_analysis({"mode":"arm","entry":"0x1000","annotations":[
            {"address":"0x1000","operation":"unsupported","condition":"al"}],"edges":[]})
        self.assertEqual(g["unsupported_count"],1)
    def test_reject_thumb(self):
        with self.assertRaises(ValueError):
            module.from_analysis({"mode":"thumb","entry":"0x1000","annotations":[],"edges":[]})
if __name__=="__main__":unittest.main()
