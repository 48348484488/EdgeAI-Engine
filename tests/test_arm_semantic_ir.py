"""ARM32 typed instruction evidence, fail-closed decoding and real ELF tests."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
def load(filename):
    path=ROOT/'tools'/filename
    spec=importlib.util.spec_from_file_location(filename[:-3],path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

sem=load('arm_semantic_ir.py')
struct=load('arm_structured_ir.py')
def ins(pc,op,args=''):
    return {'pc':hex(pc),'mnemonic':op,'operands':args}


class SemanticIRTests(unittest.TestCase):
    def test_arithmetic_and_immediates(self):
        move=sem.decode(ins(0x1000,'mov','r0, #8'))
        self.assertEqual(move['source'],{'kind':'immediate','value':8})
        add=sem.decode(ins(0x1004,'add','r1, r1, #1'))
        self.assertEqual((add['kind'],add['destination'],add['rhs']['value']),('binary','r1',1))
        self.assertFalse(add['sets_flags'])
        self.assertTrue(sem.decode(ins(0x1008,'ands','r3, r1, r2'))['sets_flags'])

    def test_flag_comparison(self):
        cmp=sem.decode(ins(0x1000,'cmp','r0, #8'))
        self.assertEqual((cmp['kind'],cmp['rhs']['value']),('flag_test',8))

    def test_predicated_move_not_unconditional(self):
        pred=sem.decode(ins(0x1000,'movne','r0, r2'))
        self.assertEqual(pred['predicate'],'ne')
        self.assertEqual(pred['kind'],'assignment')

    def test_scaled_board_address(self):
        read=sem.decode(ins(0x1000,'ldr','r2, [lr, r2, lsl #2]'))
        self.assertEqual(read['kind'],'memory_read')
        self.assertEqual(read['width_bytes'],4)
        self.assertEqual(read['address']['index'],{'kind':'scaled_register','register':'r2','shift':2})
        self.assertFalse(read['alias_proven'])

    def test_post_index_increment(self):
        read=sem.decode(ins(0x1000,'ldr','r3, [r0], #4'))
        self.assertEqual(read['address']['mode'],'post_index')
        self.assertEqual(read['address']['post_increment'],4)

    def test_invalid_address_fails_closed(self):
        bad=sem.decode(ins(0x1000,'ldr','r2, [r0, r1, ror #5]'))
        self.assertEqual(bad['kind'],'unsupported')
        self.assertEqual(sem.decode(ins(0x1004,'add','r0, r0, r1, lsl #1'))['kind'],'unsupported')

    def test_indirect_control_is_not_source_level_return_proof(self):
        ret=sem.decode(ins(0x1000,'bx','lr'))
        self.assertEqual(ret['kind'],'indirect_branch')
        self.assertTrue(ret['potential_return'])
        self.assertEqual(sem.decode(ins(0x1004,'bx','r3'))['potential_return'],False)

    def test_memory_write_and_byte_access(self):
        store=sem.decode(ins(0x1000,'str','r1, [r2, r0, lsl #2]'))
        self.assertEqual(store['kind'],'memory_write')
        self.assertEqual(sem.decode(ins(0x1004,'ldrb','r3, [r2, #1]'))['width_bytes'],1)

    def test_region_membership_and_unreachable_filter(self):
        ir={'entry':'0x1000','loops':[{'header':'0x1004','body_pcs':['0x1004','0x1008']}],
            'conditionals':[{'kind':'if_else','branch_pc':'0x1000',
                             'then_pcs':['0x1004'],'else_pcs':['0x1008']}],
            'unstructured':[]}
        rows=[ins(0x1000,'beq','0x1008'),ins(0x1004,'add','r1, r1, #1'),
              ins(0x1008,'str','r1, [r2, #4]'),ins(0x100c,'foo','?')]
        result=sem.attach(ir,rows,reachable_pcs=['0x1000','0x1004','0x1008'])
        self.assertEqual(len(result['instruction_effects']),3)
        a=result['instruction_effects'][1]
        self.assertEqual(a['region_context']['loops'],['0x1004'])
        self.assertEqual(a['region_context']['if_arms'][0]['arm'],'then')
        self.assertEqual(result['semantic_coverage']['unsupported'],0)

    def test_duplicate_instruction_rejected(self):
        ir={'entry':'0x1000','loops':[],'conditionals':[],'unstructured':[]}
        with self.assertRaisesRegex(ValueError,'duplicate'):
            sem.attach(ir,[ins(0x1000,'nop'),ins(0x1000,'nop')])

    def test_missing_reachable_instruction_rejected(self):
        ir={'entry':'0x1000','loops':[],'conditionals':[],'unstructured':[]}
        with self.assertRaisesRegex(ValueError,'missing reachable'):
            sem.attach(ir,[ins(0x1000,'nop')],reachable_pcs=['0x1000','0x1004'])

    @unittest.skipUnless(shutil.which('clang') and shutil.which('llvm-objdump'),
                         'Clang and llvm-objdump required')
    def test_compiled_arm32_fixtures_include_semantics(self):
        loop=load('arm_loop_analysis.py')
        for filename,fn,expected_kind in [
            ('tictactoe.c','winner','memory_read'),
            ('tictactoe.c','play','memory_write'),
            ('array_sum.c','sum_array','memory_read'),
        ]:
            with self.subTest(source=filename,function=fn):
                with tempfile.TemporaryDirectory() as tmp:
                    elf=Path(tmp)/'game.elf'
                    subprocess.run(['clang','--target=armv7-none-eabi','-marm','-O1',
                        '-fno-inline','-nostdlib','-fuse-ld=lld','-Wl,-Ttext=0x1000',
                        '-Wl,-e=start',str(ROOT/'examples/reverse'/filename),
                        '-o',str(elf)],check=True,capture_output=True)
                    dump=subprocess.run(['llvm-objdump','-d',str(elf)],
                                        check=True,capture_output=True,text=True).stdout
                rows=loop.disassemble_function(dump,fn)
                out=struct.analyze_instructions(rows,fn)
                self.assertEqual(out['proof_status'],'structural_only')
                self.assertEqual(len(out['instruction_effects']),loop.analyze(rows,fn)['reachable_instruction_count'])
                self.assertGreater(out['semantic_coverage']['recognized'],0)
                self.assertIn(expected_kind,{item['kind'] for item in out['instruction_effects']})

if __name__=='__main__':
    unittest.main()
