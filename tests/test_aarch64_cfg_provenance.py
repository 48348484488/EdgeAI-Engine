"""CFG-aware ARM64 reaching definition tests: paths, clobbers, boundaries."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from aarch64_cfg_provenance import analyze

TEXT = '''
1000: adrp x11, 0x870000
1004: b.eq 0x1010
1008: nop
100c: b 0x1014
1010: nop
1014: add x11, x11, #0xb0c
1018: adr x9, 0x1018
101c: ldrsw x10, [x11, x8, lsl #2]
1020: add x9, x9, x10
1024: br x9
'''


def fixture():
    spans = [(0x1000, 0x1008, 'B.cond'),
             (0x1008, 0x1010, 'B'),
             (0x1010, 0x1014, None),
             (0x1014, 0x1028, 'BR')]
    graph = {'architecture': 'AArch64', 'function': 'target', 'entry': '0x1000',
             'symbol_size_bytes': 0x28, 'code_executed': False,
             'blocks': [dict(start=hex(a), end_exclusive=hex(b),
                             size_bytes=b-a, last_instruction=hex(b-4),
                             last_control_transfer=kind)
                        for a, b, kind in spans]}
    graph['block_count'] = len(graph['blocks'])
    edges = [(0x1000, 0x1010, 'taken_candidate'),
             (0x1000, 0x1008, 'not_taken_candidate'),
             (0x1008, 0x1014, 'unconditional'),
             (0x1010, 0x1014, 'linear_candidate'),
             (0x1014, None, 'indirect_jump_unresolved')]
    graph['edges'] = [{'from': hex(s), 'to': hex(d) if d else None,
                       'kind': k, 'target_in_symbol': d is not None}
                      for s, d, k in edges]
    graph['edge_count'] = len(graph['edges'])
    indirect = {'architecture': 'AArch64', 'function': 'target',
                'entry': '0x1000', 'targets_resolved': False,
                'indirect_site_count': 1,
                'sites': [{'pc': '0x1024',
                           'pattern': 'pc_relative_indexed_table_dispatch_candidate',
                           'table_base_register': 'x11',
                           'index_register': 'x8'}]}
    return graph, indirect


class ReachingDefinitionTests(unittest.TestCase):
    def test_both_paths_preserve_constant_before_add(self):
        graph, indirect = fixture()
        result = analyze(graph, indirect, TEXT)
        row = result['sites'][0]
        self.assertEqual(result['static_cfg_base_candidates'], 1)
        self.assertEqual(row['table_base_candidate'], '0x870b0c')
        self.assertEqual((row['adrp_pc'], row['add_pc']), ('0x1000', '0x1014'))
        self.assertFalse(result['runtime_control_flow_proven'])
        self.assertFalse(result['table_bytes_read'])
        self.assertFalse(row['all_runtime_paths_proven'])

    def test_one_path_clobbers_page(self):
        graph, indirect = fixture()
        result = analyze(graph, indirect, TEXT.replace('1010: nop', '1010: mov x11, x0'))
        self.assertEqual(result['sites'][0]['status'], 'UNKNOWN_REACHING_BASE')

    def test_one_path_unknown_instruction_fails_closed(self):
        graph, indirect = fixture()
        result = analyze(graph, indirect, TEXT.replace('1010: nop', '1010: obscure'))
        self.assertEqual(result['static_cfg_base_candidates'], 0)

    def test_missing_llvm_instruction_fails_closed(self):
        graph, indirect = fixture()
        result = analyze(graph, indirect, TEXT.replace('1010: nop', ''))
        self.assertEqual(result['static_cfg_base_candidates'], 0)

    def test_call_invalidates_caller_saved_x11(self):
        graph, indirect = fixture()
        result = analyze(graph, indirect, TEXT.replace('1008: nop', '1008: bl 0x2000'))
        self.assertEqual(result['static_cfg_base_candidates'], 0)

    def test_call_preserves_callee_saved_x20(self):
        graph, indirect = fixture()
        indirect['sites'][0]['table_base_register'] = 'x20'
        changed = (TEXT.replace('x11', 'x20')
                   .replace('1008: nop', '1008: bl 0x2000'))
        result = analyze(graph, indirect, changed)
        self.assertEqual(result['static_cfg_base_candidates'], 1)

    def test_bad_internal_edge_rejected(self):
        graph, indirect = fixture()
        graph['edges'][0]['to'] = '0x1012'
        with self.assertRaisesRegex(ValueError, 'edge'):
            analyze(graph, indirect, TEXT)

    def test_dispatch_must_be_block_tail(self):
        graph, indirect = fixture()
        graph['blocks'][-1]['last_control_transfer'] = 'RET'
        with self.assertRaisesRegex(ValueError, 'CFG edge kinds'):
            analyze(graph, indirect, TEXT)

    def test_missing_branch_edge_cannot_prove_origin(self):
        graph, indirect = fixture()
        graph['edges'] = [e for e in graph['edges']
                          if e['kind'] != 'not_taken_candidate']
        graph['edge_count'] -= 1
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            analyze(graph, indirect, TEXT)

    def test_branch_target_mismatch_rejected(self):
        graph, indirect = fixture()
        with self.assertRaisesRegex(ValueError, 'target mismatch'):
            analyze(graph, indirect, TEXT.replace('b.eq 0x1010', 'b.eq 0x1014'))

    def test_postindexed_load_clobbers_table_base(self):
        graph, indirect = fixture()
        changed = TEXT.replace('1010: nop', '1010: ldr x0, [x11], #8')
        self.assertEqual(analyze(graph, indirect, changed)['static_cfg_base_candidates'], 0)

    def test_non_table_sites_not_promoted(self):
        graph, indirect = fixture()
        indirect['sites'][0]['pattern'] = 'unclassified_indirect_branch'
        result = analyze(graph, indirect, TEXT)
        self.assertEqual(result['sites'][0]['status'], 'NOT_RELATIVE_TABLE')


if __name__ == '__main__':
    unittest.main()
