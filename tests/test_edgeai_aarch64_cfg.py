import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from edgeai_aarch64_cfg import parse_instructions, branch_target, build_cfg

SAMPLE = '''  1000: 7101041f cmp w0, #0x41
  1004: 54000060 b.eq 0x1010
  1008: 97fffbfa bl 0x800 <puts@plt>
  100c: 14000002 b 0x1014
  1010: 17fffffc b 0x1000
  1014: d65f03c0 ret
'''

class CFGTests(unittest.TestCase):
    def test_parser(self):
        self.assertEqual(len(parse_instructions(SAMPLE)), 6)
        self.assertEqual(branch_target('b.eq', '0x1010 <.text>'), 0x1010)
        self.assertEqual(branch_target('tbz', 'w0, #0x0, 0x1010'), 0x1010)
    def test_blocks_and_backedge(self):
        graph = build_cfg(parse_instructions(SAMPLE), 0x1000, 0x1018)
        self.assertEqual(graph['instruction_count'], 6)
        self.assertEqual(graph['block_count'], 4)
        self.assertEqual(graph['reachable_blocks'], 4)
        self.assertEqual(graph['conditional_guards'][0]['adjacent_compare']['immediate'], 65)
        self.assertEqual(graph['backward_edges'], [{'from':'0x1010', 'to':'0x1000'}])
        self.assertEqual(graph['calls'][0]['symbol'], 'puts@plt')
    def test_fail_closed_on_gap(self):
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            build_cfg(parse_instructions(SAMPLE), 0x1000, 0x101c)
    def test_fail_closed_on_unknown_branch(self):
        bad = SAMPLE.replace('b.eq 0x1010', 'b.eq x1')
        with self.assertRaisesRegex(ValueError, 'unknown conditional'):
            build_cfg(parse_instructions(bad), 0x1000, 0x1018)
    def test_external_branch_not_fabricated(self):
        rows = parse_instructions('  1000: 14000004 b 0x1010\n')
        g = build_cfg(rows, 0x1000, 0x1004)
        self.assertEqual(g['blocks'][0]['external_successors'], ['0x1010'])
    def test_no_false_equivalence(self):
        graph = build_cfg(parse_instructions(SAMPLE), 0x1000, 0x1018)
        self.assertIn('not modeled', graph['limitations'])
        self.assertNotIn('cpp_emitted', graph)
    def test_duplicate_disassembly_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            build_cfg(parse_instructions(SAMPLE + '  1000: 7101041f cmp w0, #0x41\n'), 0x1000, 0x1018)

if __name__ == '__main__': unittest.main()
