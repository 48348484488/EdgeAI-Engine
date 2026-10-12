"""Validate CFG reconvergence, early exits, loops and unresolved control."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('arm_control_regions', ROOT/'tools'/'arm_control_regions.py')
regions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regions)


def fixture(pcs, edges, exits, returns=(), external=()):
    return {'entry': hex(pcs[0]), 'reachable_pcs': [hex(x) for x in pcs],
            'cfg_edges': [{'from':hex(a), 'to':hex(b), 'type':t} for a,b,t in edges],
            'exit_pcs': [hex(x) for x in exits],
            'conditional_returns': [{'pc':hex(x)} for x in returns],
            'external_edges': [{'from':hex(a),'to':hex(b)} for a,b in external],
            'unknown_control_pcs': []}


class RegionsTests(unittest.TestCase):
    def test_diamond_joins(self):
        g=fixture([0x1000,0x1004,0x1008,0x100c],
                  [(0x1000,0x1004,'fallthrough'),(0x1000,0x1008,'taken'),
                   (0x1004,0x100c,'flow'),(0x1008,0x100c,'flow')],[0x100c])
        a=regions.analyze(g)
        self.assertEqual(a['decision_count'],1)
        self.assertEqual(a['decisions'][0]['merge'],'0x100c')
        self.assertEqual(a['decisions'][0]['classification'],'reconverging')

    def test_early_return_has_no_merge(self):
        g=fixture([0x1000,0x1004,0x1008,0x100c],
                  [(0x1000,0x1004,'fallthrough'),(0x1000,0x1008,'taken'),
                   (0x1004,0x100c,'flow')],[0x1008,0x100c])
        a=regions.analyze(g)
        self.assertEqual(a['decisions'][0]['classification'],'exit_only')
        self.assertIsNone(a['decisions'][0]['merge'])

    def test_loop_with_exit_and_postdomination(self):
        g=fixture([0x1000,0x1004,0x1008,0x100c],
                  [(0x1000,0x1004,'flow'),(0x1004,0x1008,'taken'),
                   (0x1004,0x100c,'fallthrough'),(0x1008,0x1004,'flow')],[0x100c])
        a=regions.analyze(g)
        self.assertEqual(a['decision_count'],1)
        self.assertEqual(a['decisions'][0]['merge'],'0x100c')

    def test_conditional_return(self):
        g=fixture([0x1000,0x1004,0x1008],
                  [(0x1000,0x1004,'flow'),(0x1004,0x1008,'flow')],[0x1008],[0x1004])
        a=regions.analyze(g)
        self.assertTrue(a['decisions'][0]['conditional_return'])
        self.assertEqual(a['decisions'][0]['classification'],'exit_only')

    def test_infinite_cycle_is_not_claimed_to_reconverge(self):
        g=fixture([0x1000,0x1004,0x1008,0x100c],
                  [(0x1000,0x1004,'taken'),(0x1000,0x1008,'fallthrough'),
                   (0x1004,0x1004,'flow'),(0x1008,0x100c,'flow')],[0x100c])
        a=regions.analyze(g)
        self.assertEqual(a['decisions'][0]['classification'],'unresolved')
        self.assertEqual(a['nonterminating_nodes'],['0x1004'])

    def test_actual_arm_game(self):
        import shutil
        import subprocess
        import tempfile
        if not shutil.which('clang') or not shutil.which('llvm-objdump'):
            self.skipTest('requires LLVM ARM compiler and disassembler')
        loop_path = ROOT/'tools'/'arm_loop_analysis.py'
        ls = importlib.util.spec_from_file_location('edge_loop_analysis',loop_path)
        loops = importlib.util.module_from_spec(ls)
        ls.loader.exec_module(loops)
        with tempfile.TemporaryDirectory() as tmp:
            elf = Path(tmp)/'game.elf'
            subprocess.run(['clang','--target=armv7-none-eabi','-marm','-O1',
                '-fno-inline','-nostdlib','-fuse-ld=lld','-Wl,-Ttext=0x1000',
                '-Wl,-e,start',str(ROOT/'examples/reverse/tictactoe.c'),
                '-o',str(elf)], check=True,capture_output=True)
            dump = subprocess.run(['llvm-objdump','-d',str(elf)],
                                  check=True,capture_output=True,text=True).stdout
        winner = regions.analyze(loops.analyze(loops.disassemble_function(dump,'winner'),'winner'))
        play = regions.analyze(loops.analyze(loops.disassemble_function(dump,'play'),'play'))
        self.assertEqual(winner['decision_count'],2)
        self.assertEqual(len({x['merge'] for x in winner['decisions']}),1)
        self.assertTrue(all(x['classification']=='reconverging' for x in winner['decisions']))
        self.assertEqual(play['decision_count'],2)
        self.assertTrue(all(x['classification']=='exit_only' for x in play['decisions']))

    def test_invalid_graph_rejected(self):
        g=fixture([0x1000],[(0x1000,0x1004,'flow')],[0x1000])
        with self.assertRaisesRegex(ValueError,'outside reachable'):
            regions.analyze(g)


if __name__ == '__main__':
    unittest.main()
