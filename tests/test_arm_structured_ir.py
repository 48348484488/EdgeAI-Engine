"""Conservative structured-IR tests, plus independent compiled ARM fixtures."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('structured_ir',ROOT/'tools'/'arm_structured_ir.py')
ir=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ir)

def cfg(pcs, edges, loops=(), entry=None, unknown=()):
    return {'entry':hex(entry or pcs[0]),'reachable_pcs':[hex(x) for x in pcs],
            'cfg_edges':[{'from':hex(a),'to':hex(b),'type':kind} for a,b,kind in edges],
            'loops':list(loops),'unknown_control_pcs':[hex(x) for x in unknown]}

def regions(entry, decisions, unknown=()):
    return {'entry':hex(entry),'decisions':list(decisions),'unknown_control_pcs':[hex(x) for x in unknown]}

class StructuredIRTests(unittest.TestCase):
    def test_diamond_if_else(self):
        g=cfg([0x1000,0x1004,0x1008,0x100c],
              [(0x1000,0x1008,'taken'),(0x1000,0x1004,'fallthrough'),
               (0x1004,0x100c,'flow'),(0x1008,0x100c,'flow')])
        r=regions(0x1000,[{'branch_pc':'0x1000','taken':'0x1008',
                           'fallthrough':'0x1004','merge':'0x100c','classification':'reconverging'}])
        out=ir.build(g,r)
        self.assertEqual(out['conditionals'][0]['kind'],'if_else')
        self.assertEqual(out['conditionals'][0]['then_pcs'],['0x1008'])
        self.assertEqual(out['conditionals'][0]['else_pcs'],['0x1004'])
        self.assertEqual(out['unstructured'],[])

    def test_loop_latch(self):
        g=cfg([0x1000,0x1004,0x1008,0x100c],
              [(0x1000,0x1004,'flow'),(0x1004,0x1008,'flow'),
               (0x1008,0x1004,'taken'),(0x1008,0x100c,'fallthrough')],
              loops=[{'header':'0x1004','back_edge_latches':['0x1008'],
                      'instruction_addresses':['0x1004','0x1008']}])
        r=regions(0x1000,[{'branch_pc':'0x1008','taken':'0x1004',
                           'fallthrough':'0x100c','merge':'0x100c',
                           'classification':'reconverging'}])
        out=ir.build(g,r)
        self.assertEqual(out['conditionals'][0]['kind'],'loop_branch')
        self.assertEqual(out['loops'][0]['header'],'0x1004')

    def test_exit_dispatch(self):
        g=cfg([0x1000,0x1004,0x1008],
              [(0x1000,0x1008,'taken'),(0x1000,0x1004,'fallthrough')])
        r=regions(0x1000,[{'branch_pc':'0x1000','taken':'0x1008',
                           'fallthrough':'0x1004','merge':None,'classification':'exit_only'}])
        self.assertEqual(ir.build(g,r)['conditionals'][0]['kind'],'exit_dispatch')

    def test_nested_loops(self):
        g=cfg([0x1000,0x1004,0x1008,0x100c,0x1010,0x1014],
              [(0x1000,0x1004,'flow'),(0x1004,0x1008,'flow'),(0x1008,0x100c,'flow'),
               (0x100c,0x1008,'flow'),(0x100c,0x1010,'flow'),
               (0x1010,0x1004,'flow'),(0x1010,0x1014,'flow')],
              loops=[{'header':'0x1004','back_edge_latches':['0x1010'],
                      'instruction_addresses':['0x1004','0x1008','0x100c','0x1010']},
                     {'header':'0x1008','back_edge_latches':['0x100c'],
                      'instruction_addresses':['0x1008','0x100c']}])
        self.assertEqual(ir.build(g,regions(0x1000,[]))['loops'][1]['parent_header'],'0x1004')

    def test_overlapping_arms_fail_closed(self):
        g=cfg([0x1000,0x1004,0x1008,0x100c],
              [(0x1000,0x1004,'fallthrough'),(0x1000,0x1008,'taken'),
               (0x1004,0x1008,'flow'),(0x1008,0x100c,'flow')])
        r=regions(0x1000,[{'branch_pc':'0x1000','taken':'0x1008',
                           'fallthrough':'0x1004','merge':'0x100c','classification':'reconverging'}])
        out=ir.build(g,r)
        self.assertFalse(out['conditionals'])
        self.assertEqual(out['unstructured'][0]['branch_pc'],'0x1000')

    def test_unknown_control_flow_fail_closed(self):
        self.assertEqual(ir.build(cfg([0x1000],[],unknown=[0x1000]),
                                  regions(0x1000,[]))['proof_status'],'unknown_control_flow')

    def test_invalid_branch_target_rejected(self):
        g=cfg([0x1000,0x1004,0x1008],[(0x1000,0x1004,'fallthrough')])
        r=regions(0x1000,[{'branch_pc':'0x1000','taken':'0x1008',
                           'fallthrough':'0x1004','classification':'exit_only'}])
        with self.assertRaisesRegex(ValueError,'decision edge'):ir.build(g,r)

    def test_budget(self):
        with self.assertRaisesRegex(ValueError,'size'):
            ir.build(cfg([0x1000],[]),regions(0x1000,[]),max_nodes=0)

    def test_mismatch_entry(self):
        with self.assertRaisesRegex(ValueError,'mismatched'):
            ir.build(cfg([0x1000,0x1004],[(0x1000,0x1004,'flow')]),regions(0x1004,[]))

    @unittest.skipUnless(shutil.which('clang') and shutil.which('llvm-objdump'),
                         'Clang and llvm-objdump required for compiled ARM tests')
    def test_real_game_and_independent_array_sum(self):
        for source, functions in [('tictactoe.c',('winner','play','start')),
                                  ('array_sum.c',('sum_array','start'))]:
            with self.subTest(source=source):
                with tempfile.TemporaryDirectory() as tmp:
                    elf=Path(tmp)/'fixture.elf'
                    subprocess.run(['clang','--target=armv7-none-eabi','-marm','-O1',
                        '-fno-inline','-nostdlib','-fuse-ld=lld',
                        '-Wl,-Ttext=0x1000','-Wl,-e=start',
                        str(ROOT/'examples/reverse'/source),'-o',str(elf)],
                        check=True,capture_output=True)
                    dump=subprocess.run(['llvm-objdump','-d',str(elf)],
                                        check=True,capture_output=True,text=True).stdout
                ls=importlib.util.spec_from_file_location('arm_loops',ROOT/'tools'/'arm_loop_analysis.py')
                loop=importlib.util.module_from_spec(ls);ls.loader.exec_module(loop)
                for function in functions:
                    result=ir.analyze_instructions(loop.disassemble_function(dump,function),function)
                    self.assertEqual(result['proof_status'],'structural_only')
                    self.assertTrue(result['entry'].startswith('0x'))
                    if function in ('winner','sum_array'):
                        self.assertEqual(len(result['loops']),1)

if __name__=='__main__':unittest.main()
