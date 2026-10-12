"""Generic ARM natural-loop and memory indexing regression tests."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('arm_loop_analysis', ROOT / 'tools' / 'arm_loop_analysis.py')
loops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loops)


def ins(pc, op, args=''):
    return {'pc': hex(pc), 'mnemonic': op, 'operands': args}


class TestLoopAnalysis(unittest.TestCase):
    def test_simple_counter_loop(self):
        seq = [ins(0x1000, 'mov', 'r1, #0'),
               ins(0x1004, 'ldr', 'r2, [r0, r1, lsl #2]'),
               ins(0x1008, 'add', 'r1, r1, #1'),
               ins(0x100c, 'cmp', 'r1, #8'),
               ins(0x1010, 'bne', '0x1004'),
               ins(0x1014, 'bx', 'lr')]
        result = loops.analyze(seq, function='arbitrary')
        self.assertEqual(result['loop_count'], 1)
        self.assertEqual(result['loops'][0]['header'], '0x1004')
        self.assertEqual(result['loops'][0]['back_edge_latches'], ['0x1010'])
        self.assertEqual(result['loops'][0]['counter_candidates'][0]['compare_immediate'], 8)
        self.assertEqual(result['memory_accesses'][0]['scale'], 4)

    def test_nested_loops_and_unreachable_instructions(self):
        seq = [ins(0x1000, 'mov', 'r0, #0'),
               ins(0x1004, 'cmp', 'r0, #3'),
               ins(0x1008, 'beq', '0x1034'),
               ins(0x100c, 'mov', 'r1, #0'),
               ins(0x1010, 'cmp', 'r1, #2'),
               ins(0x1014, 'beq', '0x1024'),
               ins(0x1018, 'add', 'r1, r1, #1'),
               ins(0x101c, 'b', '0x1010'),
               ins(0x1020, 'nop'),
               ins(0x1024, 'add', 'r0, r0, #1'),
               ins(0x1028, 'b', '0x1004'),
               ins(0x102c, 'nop'),
               ins(0x1030, 'nop'),
               ins(0x1034, 'bx', 'lr')]
        result = loops.analyze(seq)
        self.assertEqual(result['loop_count'], 2)
        self.assertEqual([x['header'] for x in result['loops']], ['0x1004', '0x1010'])
        self.assertEqual(result['reachable_instruction_count'], 11)
        self.assertTrue(all('0x1020' not in x['instruction_addresses'] for x in result['loops']))

    def test_irreducible_cycle_is_not_a_proven_natural_loop(self):
        seq = [ins(0x1000, 'beq', '0x100c'),
               ins(0x1004, 'b', '0x1010'),
               ins(0x1008, 'nop'),
               ins(0x100c, 'b', '0x1010'),
               ins(0x1010, 'bne', '0x1004'),
               ins(0x1014, 'bx', 'lr')]
        self.assertEqual(loops.analyze(seq)['loop_count'], 0)

    def test_unverified_indirect_branch_is_reported(self):
        result = loops.analyze([ins(0x1000, 'bx', 'r3')])
        self.assertEqual(result['unknown_control_pcs'], ['0x1000'])
        self.assertEqual(result['loop_count'], 0)

    def test_conditional_return_keeps_fallthrough_path(self):
        seq = [ins(0x1000, 'cmp', 'r0, #0'),
               ins(0x1004, 'bxeq', 'lr'),
               ins(0x1008, 'ldr', 'r1, [r2, #4]'),
               ins(0x100c, 'bx', 'lr')]
        result = loops.analyze(seq)
        self.assertEqual(result['reachable_instruction_count'], 4)
        self.assertEqual(result['conditional_returns'][0]['condition'], 'eq')
        self.assertFalse(result['unknown_control_pcs'])

    def test_bad_duplicate_pc_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            loops.analyze([ins(0x1000, 'nop'), ins(0x1000, 'bx', 'lr')])

    @unittest.skipUnless(shutil.which('clang') and shutil.which('llvm-objdump'),
                         'LLVM ARM compiler and disassembler are required')
    def test_real_compiled_game_has_one_winner_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            elf = Path(tmp) / 'game.elf'
            subprocess.run(['clang', '--target=armv7-none-eabi', '-marm', '-O1',
                '-fno-inline', '-nostdlib', '-fuse-ld=lld', '-Wl,-Ttext=0x1000',
                '-Wl,-e=start', str(ROOT / 'examples/reverse/tictactoe.c'), '-o', str(elf)],
                check=True, capture_output=True)
            dump = subprocess.run(['llvm-objdump', '-d', str(elf)],
                                  check=True, capture_output=True, text=True).stdout
        winner = loops.analyze(loops.disassemble_function(dump, 'winner'), 'winner')
        play = loops.analyze(loops.disassemble_function(dump, 'play'), 'play')
        start = loops.analyze(loops.disassemble_function(dump, 'start'), 'start')
        self.assertEqual(winner['loop_count'], 1)
        self.assertEqual(play['loop_count'], 0)
        self.assertEqual(start['loop_count'], 0)
        self.assertEqual(winner['reachable_instruction_count'], 29)
        self.assertEqual(len([m for m in winner['memory_accesses'] if m['operation'] == 'ldrb']), 3)
        self.assertEqual(len([m for m in winner['memory_accesses'] if m['operation'] == 'ldr']), 3)
        self.assertEqual(winner['loops'][0]['counter_candidates'][0]['compare_immediate'], 8)
        self.assertEqual(len(winner['loops'][0]['exit_edges']), 2)
        self.assertFalse(winner['unknown_control_pcs'])

    @unittest.skipUnless(shutil.which('clang') and shutil.which('llvm-objdump'),
                         'LLVM ARM compiler and disassembler are required')
    def test_changing_real_loop_back_edge_changes_detected_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            elf = Path(tmp) / 'game.elf'
            subprocess.run(['clang', '--target=armv7-none-eabi', '-marm', '-O1',
                '-fno-inline', '-nostdlib', '-fuse-ld=lld', '-Wl,-Ttext=0x1000',
                '-Wl,-e=start', str(ROOT / 'examples/reverse/tictactoe.c'), '-o', str(elf)],
                check=True, capture_output=True)
            dump = subprocess.run(['llvm-objdump', '-d', str(elf)],
                                  check=True, capture_output=True, text=True).stdout
        instructions = loops.disassemble_function(dump, 'winner')
        modified = [dict(i) for i in instructions]
        back = next(i for i in modified if i['mnemonic'] == 'bne')
        back['mnemonic'] = 'nop'
        back['operands'] = ''
        self.assertEqual(loops.analyze(modified)['loop_count'], 0)


if __name__ == '__main__':
    unittest.main()
