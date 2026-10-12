import importlib.util
from pathlib import Path
import unittest
p=Path(__file__).resolve().parents[1]/"tools"/"arm_graph_structure.py"
s=importlib.util.spec_from_file_location("graph_structure",p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
    def test_split_and_return(self):
        g={"entry":"0x1000","nodes":[{"address":"0x1000","op":"branch","condition":"hi"},{"address":"0x1004","op":"indirect_branch","register":"r14"},{"address":"0x1010","op":"indirect_branch","register":"r14"}],"edges":[{"from":"0x1000","to":"0x1010","type":"taken"},{"from":"0x1000","to":"0x1004","type":"fallthrough"}]}
        result=m.analyze(g)
        self.assertEqual(result["reachable_nodes"],3)
        self.assertEqual(result["decision_candidates"][0]["condition"],"hi")
        self.assertEqual(result["returns"],["0x1004","0x1010"])
    def test_unsupported(self):
        result=m.analyze({"entry":"0x1000","nodes":[{"address":"0x1000","op":"unsupported"}],"edges":[]})
        self.assertEqual(result["unsupported_reachable"],["0x1000"])
if __name__=="__main__":unittest.main()
