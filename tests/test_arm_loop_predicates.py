"""Validate generic ARM32 counter/backedge candidates against CFG and real ELF."""
import copy
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(
        'loop_predicate_' + name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


loops = load('arm_loop_analysis')
predicates = load('arm_loop_predicates')
semantic = load('arm_semantic_ir')
structured = load('arm_structured_ir')


def fixture():
    instructions = [
        {'pc':'0x1000','mnemonic':'add','operands':'r1, r1, #1'},
        {'pc':'0x1004','mnemonic':'cmp','operands':'r1, #8'},
        {'pc':'0x1008','mnemonic':'bne','operands':'0x1000'},
        {'pc':'0x100c','mnemonic':'bx','operands':'lr'},
    ]
    effects = [semantic.decode(item) for item in instructions]
    cfg = {'entry':'0x1000','reachable_pcs':[x['pc'] for x in instructions],
           'cfg_edges':[
               {'from':'0x1000','to':'0x1004','type':'flow'},
               {'from':'0x1004','to':'0x1008','type':'flow'},
               {'from':'0x1008','to':'0x1000','type':'taken'},
               {'from':'0x1008','to':'0x100c','type':'fallthrough'}]}
    outline = {'entry':'0x1000','instruction_effects':effects,
               'loops':[{'header':'0x1000',
                         'body_pcs':['0x1000','0x1004','0x1008'],
                         'latches':['0x1008']}]}
    return cfg,outline


class LoopPredicateTests(unittest.TestCase):
    def test_candidate_counter_and_cmp(self):
        cfg, ir = fixture()
        result = predicates.analyze(cfg,ir)['loops'][0]['latches'][0]
        self.assertEqual((result['counter_register'],result['delta'],result['bound']),
                         ('r1',1,8))
        self.assertEqual(result['status'],'counter_candidate')
        self.assertEqual(result['backedge_predicate'],'ne')
        self.assertFalse(result['iteration_count_proven'])

    def test_tampered_target_rejected_as_candidate(self):
        cfg,ir = fixture()
        ir['instruction_effects'][2]['target'] = '0x2000'
        result = predicates.analyze(cfg,ir)['loops'][0]['latches'][0]
        self.assertEqual(result['status'],'unsupported_backedge_predicate')

    def test_nonunique_increment_rejected(self):
        cfg,ir=fixture()
        ir['instruction_effects'][1] = dict(ir['instruction_effects'][1],
           kind='binary',operation='add',destination='r1',
           lhs='r1',rhs={'kind':'immediate','value':1})
        result=predicates.analyze(cfg,ir)['loops'][0]['latches'][0]
        self.assertEqual(result['status'],'flag_source_not_supported')

    def test_broken_edge_rejected(self):
        cfg,ir=fixture()
        cfg['cfg_edges'][2]['type']='flow'
        result=predicates.analyze(cfg,ir)['loops'][0]['latches'][0]
        self.assertEqual(result['status'],'unverified_taken_backedge')

    def test_unknown_predecessors_not_claimed(self):
        cfg,ir=fixture()
        cfg['cfg_edges'].append({'from':'0x1000','to':'0x1008','type':'flow'})
        result=predicates.analyze(cfg,ir)['loops'][0]['latches'][0]
        self.assertEqual(result['status'],'ambiguous_flag_producer')

    def test_cfg_mismatch_rejected(self):
        cfg,ir=fixture()
        ir['entry']='0x1004'
        with self.assertRaisesRegex(ValueError,'entries'):
            predicates.analyze(cfg,ir)

    @unittest.skipUnless(shutil.which('clang') and shutil.which('llvm-objdump'),
                         'ARM32 clang and objdump needed')
    def test_real_compiled_winner_and_sum_array(self):
        for name,function,delta,bound,mode,early in [
            ('tictactoe.c','winner',1,8,'cmp_after_update',True),
            ('array_sum.c','sum_array',-1,0,'update_sets_zero',False)
        ]:
            with self.subTest(function=function):
                with tempfile.TemporaryDirectory() as tmp:
                    binary=Path(tmp)/'sample.elf'
                    subprocess.run(['clang','--target=armv7-none-eabi','-marm',
                        '-O1','-fno-inline','-nostdlib','-fuse-ld=lld',
                        '-Wl,-Ttext=0x1000','-Wl,-e=start',
                        str(ROOT/'examples/reverse'/name),'-o',str(binary)],
                        check=True,capture_output=True)
                    dump=subprocess.run(['llvm-objdump','-d',str(binary)],
                                        check=True,capture_output=True,text=True).stdout
                ins=loops.disassemble_function(dump,function)
                complete=structured.analyze_instructions(ins,function)
                self.assertEqual(len(complete['loop_predicates']['loops']),1)
                loop=complete['loop_predicates']['loops'][0]
                candidates=[x for x in loop['latches'] if x['status']=='counter_candidate']
                self.assertEqual(len(candidates),1,loop)
                item=candidates[0]
                self.assertEqual((item['counter_register'],item['delta'],item['bound'],item['compare_mode']),
                                 ('r1',delta,bound,mode))
                self.assertEqual(bool(loop['early_exit_edges']),early)
                self.assertFalse(item['iteration_count_proven'])
                self.assertTrue(loop['memory_accesses'])


if __name__ == '__main__':
    unittest.main()
