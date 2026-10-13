"""Regression tests for ARM32 symbolic register flow and branch predicates."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / 'tools' / (name + '.py')
    spec = importlib.util.spec_from_file_location('edgeai_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sem = load('arm_semantic_ir')
flow = load('arm_register_flow_ir')


def instruction(pc, mnemonic, operands=''):
    return sem.decode({'pc':hex(pc),'mnemonic':mnemonic,'operands':operands})


def run(seq, edges):
    decoded = [instruction(*ins) for ins in seq]
    outline = {'entry':decoded[0]['pc'], 'instruction_effects':decoded}
    cfg = {'entry':outline['entry'], 'reachable_pcs':[ins['pc'] for ins in decoded],
           'cfg_edges':[{'from':hex(src),'to':hex(dst),'type':kind}
                        for src,dst,kind in edges]}
    return flow.analyze(cfg, outline)['register_flow']


class RegisterFlowTests(unittest.TestCase):
    def test_add_cmp_bne_symbolic_origin(self):
        seq = [(0x1000,'add','r1, r0, #1'),(0x1004,'cmp','r1, #8'),
               (0x1008,'bne','0x1010'),(0x100c,'mov','r2, #0'),
               (0x1010,'bx','lr')]
        edges = [(0x1000,0x1004,'flow'),(0x1004,0x1008,'flow'),
                 (0x1008,0x100c,'fallthrough'),(0x1008,0x1010,'taken'),
                 (0x100c,0x1010,'flow')]
        result = run(seq,edges)
        cond = result['branch_conditions'][0]
        self.assertEqual(cond['predicate'],'ne')
        self.assertEqual(cond['source']['left']['operation'],'add')
        self.assertEqual(cond['source']['left']['left']['register'],'r0')
        self.assertEqual(cond['source']['right']['value'],8)
        self.assertEqual(cond['status'],'symbolic_expression_only')
        self.assertIsNone(cond['edge_proven'])

    def test_constant_cmp_prunes_impossible_edge(self):
        seq = [(0x1000,'mov','r0, #5'),(0x1004,'cmp','r0, #5'),
               (0x1008,'bne','0x1010'),(0x100c,'mov','r1, #2'),
               (0x1010,'bx','lr')]
        edges = [(0x1000,0x1004,'flow'),(0x1004,0x1008,'flow'),
                 (0x1008,0x1010,'taken'),(0x1008,0x100c,'fallthrough'),
                 (0x100c,0x1010,'flow')]
        result = run(seq,edges)
        self.assertEqual(result['branch_conditions'][0]['edge_proven'],'fallthrough')
        self.assertEqual(result['in_states']['0x1010']['r1']['value'],2)

    def test_conflicting_constants_join_to_unknown(self):
        seq = [(0x1000,'cmp','r0, #0'),(0x1004,'beq','0x1010'),
               (0x1008,'mov','r1, #5'),(0x100c,'b','0x1014'),
               (0x1010,'mov','r1, #6'),(0x1014,'cmp','r1, #5'),
               (0x1018,'bx','lr')]
        edges = [(0x1000,0x1004,'flow'),(0x1004,0x1010,'taken'),
                 (0x1004,0x1008,'fallthrough'),(0x1008,0x100c,'flow'),
                 (0x100c,0x1014,'flow'),(0x1010,0x1014,'flow'),
                 (0x1014,0x1018,'flow')]
        result = run(seq,edges)
        self.assertNotIn('r1',result['in_states']['0x1014'])

    def test_unknown_instruction_invalidates_flags(self):
        seq = [(0x1000,'mov','r1, #5'),(0x1004,'unknown','???'),
               (0x1008,'cmp','r1, #5'),(0x100c,'bne','0x1010'),
               (0x1010,'bx','lr')]
        edges = [(seq[i][0],seq[i+1][0],'flow') for i in range(len(seq)-1)]
        result = run(seq,edges)
        self.assertEqual(result['branch_conditions'][0]['status'],'unknown_flags')
        self.assertEqual(result['unknown_instruction_pcs'],['0x1004'])

    def test_memory_read_has_origin_not_value_proof(self):
        seq = [(0x1000,'ldr','r3, [r2, r0, lsl #2]'),
               (0x1004,'cmp','r3, #0'),(0x1008,'beq','0x1010'),
               (0x100c,'bx','lr'),(0x1010,'bx','lr')]
        edges = [(0x1000,0x1004,'flow'),(0x1004,0x1008,'flow'),
                 (0x1008,0x100c,'fallthrough'),(0x1008,0x1010,'taken')]
        result = run(seq,edges)
        self.assertEqual(result['branch_conditions'][0]['source']['left']['source_pc'],'0x1000')
        self.assertIsNone(result['branch_conditions'][0]['edge_proven'])

    def test_calls_clobber_caller_saved_registers(self):
        seq = [(0x1000,'mov','r0, #4'),(0x1004,'bl','0x9000'),
               (0x1008,'cmp','r0, #4'),(0x100c,'bx','lr')]
        edges = [(0x1000,0x1004,'flow'),(0x1004,0x1008,'flow'),
                 (0x1008,0x100c,'flow')]
        self.assertNotIn('r0',run(seq,edges)['in_states']['0x1008'])

    def test_predicated_move_invalidates_destination(self):
        seq = [(0x1000,'mov','r0, #4'),(0x1004,'movne','r0, #5'),
               (0x1008,'cmp','r0, #4'),(0x100c,'bx','lr')]
        edges = [(seq[i][0],seq[i+1][0],'flow') for i in range(len(seq)-1)]
        self.assertNotIn('r0',run(seq,edges)['in_states']['0x1008'])

    def test_back_edge_reaches_fixed_point(self):
        seq = [(0x1000,'mov','r1, #0'),(0x1004,'add','r1, r1, #1'),
               (0x1008,'cmp','r1, #8'),(0x100c,'bne','0x1004'),
               (0x1010,'bx','lr')]
        edges = [(0x1000,0x1004,'flow'),(0x1004,0x1008,'flow'),
                 (0x1008,0x100c,'flow'),(0x100c,0x1004,'taken'),
                 (0x100c,0x1010,'fallthrough')]
        result = run(seq,edges)
        self.assertNotIn('r1',result['in_states']['0x1004'])
        self.assertLessEqual(result['analyzed_instructions'],5)

    def test_unsigned_32bit_add_wraparound(self):
        seq = [(0x1000,'mov','r0, #0xffffffff'),
               (0x1004,'add','r0, r0, #1'),(0x1008,'bx','lr')]
        edges = [(0x1000,0x1004,'flow'),(0x1004,0x1008,'flow')]
        self.assertEqual(run(seq,edges)['in_states']['0x1008']['r0']['value'],0)

    @unittest.skipUnless(shutil.which('clang') and shutil.which('llvm-objdump'),
                         'ARM32 Clang and llvm-objdump required')
    def test_compiled_add_cmp_bne_dependency(self):
        loops = load('arm_loop_analysis')
        structured = load('arm_structured_ir')
        with tempfile.TemporaryDirectory() as temp:
            elf = Path(temp)/'guard.elf'
            subprocess.run(['clang','--target=armv7-none-eabi','-marm',
                '-nostdlib','-fuse-ld=lld','-Wl,-Ttext=0x1000',
                '-Wl,-e,start',str(ROOT/'examples/reverse/arm_branch_increment.S'),
                '-o',str(elf)],check=True,capture_output=True)
            listing = subprocess.run(['llvm-objdump','-d',str(elf)],
                                     check=True,capture_output=True,text=True).stdout
        ins = loops.disassemble_function(listing,'increment_guard')
        output = structured.analyze_instructions(ins,'increment_guard')
        branches = output['register_flow']['branch_conditions']
        self.assertEqual(len(branches),1)
        predicate = branches[0]
        self.assertEqual(predicate['predicate'],'ne')
        self.assertEqual(predicate['source']['left']['operation'],'add')
        self.assertEqual(predicate['source']['left']['left']['register'],'r0')
        self.assertEqual(predicate['source']['right']['value'],8)
        self.assertIsNone(predicate['edge_proven'])

    @unittest.skipUnless(shutil.which('clang') and shutil.which('llvm-objdump'),
                         'ARM32 Clang and llvm-objdump required')
    def test_compiled_arm32_function_reports(self):
        loops = load('arm_loop_analysis')
        structured = load('arm_structured_ir')
        for filename, functions in [('tictactoe.c',('play','winner')),
                                    ('array_sum.c',('sum_array',))]:
            with tempfile.TemporaryDirectory() as tmp:
                elf = Path(tmp)/'test.elf'
                subprocess.run(['clang','--target=armv7-none-eabi','-marm','-O1',
                    '-fno-inline','-nostdlib','-fuse-ld=lld',
                    '-Wl,-Ttext=0x1000','-Wl,-e=start',
                    str(ROOT/'examples/reverse'/filename),'-o',str(elf)],
                    check=True,capture_output=True)
                dis = subprocess.run(['llvm-objdump','-d',str(elf)],
                                     check=True,capture_output=True,text=True).stdout
            for function in functions:
                with self.subTest(function=function):
                    instructions = loops.disassemble_function(dis,function)
                    result = structured.analyze_instructions(instructions,function)
                    regflow = result['register_flow']
                    self.assertGreater(regflow['analyzed_instructions'],0)
                    self.assertLessEqual(regflow['analyzed_instructions'],
                                         len(result['instruction_effects']))
                    self.assertIsInstance(regflow['branch_conditions'],list)
                    self.assertIn('no memory alias proof',regflow['scope'])


if __name__=='__main__':
    unittest.main()
