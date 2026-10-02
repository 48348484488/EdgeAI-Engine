import sys,importlib.util,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
class CapabilityGate(unittest.TestCase):
    def test_safe_task_evaluation_present(self):
        self.assertIsNotNone(importlib.util.find_spec('capability_v06'))
if __name__=='__main__':unittest.main()
from capability_v06 import restricted_expression,score_task,tasks
class SafeTaskContract(unittest.TestCase):
    def test_allowed_expression(self):
        self.assertEqual(restricted_expression('a*a-b*b',dict(a=5,b=3)),16)
    def test_rejects_calls_attributes_comprehensions_and_powers(self):
        for s in ['__import__("os")','a.__class__','[x for x in a]','2**100000000','open("x")']:
            with self.assertRaises((ValueError,SyntaxError)):restricted_expression(s,dict(a=5,b=2))
    def test_reference_answers_pass_and_wrong_answers_fail(self):
        for t in tasks():
            expected=t.get('reference_expression',t.get('expected','')).encode()
            self.assertTrue(score_task(t,expected),t['id']);self.assertFalse(score_task(t,b'nonsense'),t['id'])
