"""Verify ARM flag-setting arithmetic and shifts, including compiled ELF."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    path = ROOT / 'tools' / (name + '.py')
    spec = importlib.util.spec_from_file_location('flags_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sem = load('arm_semantic_ir')
flow = load('arm_register_flow_ir')


def evaluate(operations, branch_pc=None, taken=None):
    effects = [sem.decode({'pc': hex(pc), 'mnemonic': op, 'operands': args})
               for pc, op, args in operations]
    edges = []
    for i, (pc, _, _) in enumerate(operations[:-1]):
        edges.append({'from': hex(pc), 'to': hex(operations[i+1][0]),
                      'type': 'fallthrough' if pc == branch_pc else 'flow'})
        if pc == branch_pc:
            edges.append({'from': hex(pc), 'to': hex(taken), 'type': 'taken'})
    outline = {'entry': effects[0]['pc'], 'instruction_effects': effects}
    cfg = {'entry': outline['entry'], 'reachable_pcs': [x['pc'] for x in effects],
           'cfg_edges': edges}
    return flow.analyze(cfg, outline)['register_flow']


class FlagTests(unittest.TestCase):
    def test_subs_zero_proves_branch(self):
        rows = [(0x1000,'mov','r0, #1'),(0x1004,'subs','r0, r0, #1'),
                (0x1008,'beq','0x1010'),(0x100c,'nop',''),(0x1010,'bx','lr')]
        output = evaluate(rows, 0x1008, 0x1010)
        self.assertEqual(output['branch_conditions'][0]['edge_proven'], 'taken')

    def test_subs_symbolic_does_not_prove_branch(self):
        rows = [(0x1000,'subs','r1, r0, #1'),(0x1004,'bne','0x100c'),
                (0x1008,'nop',''),(0x100c,'bx','lr')]
        branch = evaluate(rows, 0x1004, 0x100c)['branch_conditions'][0]
        self.assertEqual(branch['source']['operation'], 'zero_test')
        self.assertEqual(branch['source']['left']['operation'], 'sub')
        self.assertIsNone(branch['edge_proven'])

    def test_unsigned_cmp_hi(self):
        rows = [(0x1000,'mov','r0, #9'),(0x1004,'cmp','r0, #8'),
                (0x1008,'bhi','0x1010'),(0x100c,'nop',''),(0x1010,'bx','lr')]
        self.assertEqual(evaluate(rows, 0x1008, 0x1010)['branch_conditions'][0]['edge_proven'],'taken')

    def test_signed_cmp_lt(self):
        rows = [(0x1000,'mov','r0, #0xffffffff'),(0x1004,'cmp','r0, #0'),
                (0x1008,'blt','0x1010'),(0x100c,'nop',''),(0x1010,'bx','lr')]
        self.assertEqual(evaluate(rows, 0x1008, 0x1010)['branch_conditions'][0]['edge_proven'],'taken')

    def test_shift_flags_and_constant(self):
        rows = [(0x1000,'mov','r0, #8'),(0x1004,'lsrs','r1, r0, #1'),
                (0x1008,'bne','0x1010'),(0x100c,'nop',''),(0x1010,'bx','lr')]
        result = evaluate(rows, 0x1008, 0x1010)
        self.assertEqual(result['in_states']['0x1008']['r1']['value'], 4)
        self.assertEqual(result['branch_conditions'][0]['edge_proven'], 'taken')

    def test_shift_symbolic_origin(self):
        rows = [(0x1000,'lsr','r1, r0, #1'),(0x1004,'cmp','r1, #4'),
                (0x1008,'bne','0x1010'),(0x100c,'nop',''),(0x1010,'bx','lr')]
        compare = evaluate(rows, 0x1008, 0x1010)['branch_conditions'][0]['source']
        self.assertEqual(compare['left']['kind'],'shift_expression')

    def test_signed_shift_31(self):
        rows = [(0x1000,'mov','r0, #0x80000000'),
                (0x1004,'asr','r1, r0, #31'),(0x1008,'bx','lr')]
        self.assertEqual(evaluate(rows)['in_states']['0x1008']['r1']['value'],0xffffffff)

    def test_tst_zero(self):
        rows = [(0x1000,'mov','r0, #2'),(0x1004,'tst','r0, #1'),
                (0x1008,'beq','0x1010'),(0x100c,'nop',''),(0x1010,'bx','lr')]
        self.assertEqual(evaluate(rows,0x1008,0x1010)['branch_conditions'][0]['edge_proven'],'taken')

    def test_adds_overflow_to_zero(self):
        rows = [(0x1000,'mov','r0, #0xffffffff'),(0x1004,'adds','r0, r0, #1'),
                (0x1008,'beq','0x1010'),(0x100c,'nop',''),(0x1010,'bx','lr')]
        self.assertEqual(evaluate(rows,0x1008,0x1010)['branch_conditions'][0]['edge_proven'],'taken')

    def test_movs_sets_zero(self):
        rows = [(0x1000,'movs','r0, #0'),(0x1004,'beq','0x100c'),
                (0x1008,'nop',''),(0x100c,'bx','lr')]
        self.assertEqual(evaluate(rows,0x1004,0x100c)['branch_conditions'][0]['edge_proven'],'taken')

    def test_invalid_shift_cannot_prove(self):
        rows = [(0x1000,'mov','r1, #8'),(0x1004,'lsrs','r1, r1, #33'),
                (0x1008,'beq','0x1010'),(0x100c,'nop',''),(0x1010,'bx','lr')]
        result = evaluate(rows,0x1008,0x1010)
        self.assertNotIn('r1',result['in_states']['0x1008'])
        self.assertEqual(result['branch_conditions'][0]['status'],'unknown_flags')

    def test_zero_only_does_not_fake_carry(self):
        rows = [(0x1000,'mov','r0, #9'),(0x1004,'subs','r0, r0, #1'),
                (0x1008,'bhi','0x1010'),(0x100c,'nop',''),(0x1010,'bx','lr')]
        self.assertEqual(evaluate(rows,0x1008,0x1010)['branch_conditions'][0]['status'],'unknown_flags')

    @unittest.skipUnless(shutil.which('clang') and shutil.which('llvm-objdump'), 'LLVM required')
    def test_three_real_arm32_flag_functions(self):
        loops = load('arm_loop_analysis')
        structured = load('arm_structured_ir')
        with tempfile.TemporaryDirectory() as tmp:
            elf = Path(tmp)/'flags.elf'
            subprocess.run(['clang','--target=armv7-none-eabi','-marm',
                '-nostdlib','-fuse-ld=lld','-Wl,-Ttext=0x1000','-Wl,-e,start',
                str(ROOT/'examples/reverse/arm_flags_reference.S'),'-o',str(elf)],
                check=True,capture_output=True)
            listing = subprocess.run(['llvm-objdump','-d',str(elf)],
                                     check=True,capture_output=True,text=True).stdout
        for function, condition, branch in [
            ('sub_flag_guard','eq','taken'),
            ('unsigned_flag_guard','hi','taken'),
            ('shifted_flag_guard','eq','fallthrough'),
        ]:
            with self.subTest(function=function):
                instructions = loops.disassemble_function(listing,function)
                result = structured.analyze_instructions(instructions,function)
                cases = result['register_flow']['branch_conditions']
                self.assertEqual(len(cases),1)
                self.assertEqual(cases[0]['predicate'],condition)
                self.assertEqual(cases[0]['edge_proven'],branch)
                self.assertEqual(result['semantic_coverage']['unsupported'],0)


if __name__=='__main__':
    unittest.main()
