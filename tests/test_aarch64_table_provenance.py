"""Static AArch64 table base provenance: positive and fail-closed tests."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_table_provenance import analyze

SITE={"pc":"0x101c","pattern":"pc_relative_indexed_table_dispatch_candidate",
      "table_base_register":"x11", "index_register":"x8"}
INPUT={"architecture":"AArch64","function":"JNI_OnLoad","entry":"0x1000",
       "indirect_site_count":2,"targets_resolved":False,
       "sites":[SITE,{"pc":"0x1024","pattern":"unresolved_indirect_call"}]}
BASE='''
1000: adrp x11, 0x870000
1004: add x11, x11, #0xb0c
1008: mov x10, x8
100c: b 0x1010
1010: adr x9, 0x1010
1014: ldrsw x10, [x11, x8, lsl #2]
1018: add x9, x9, x10
101c: br x9
1024: blr x7
'''

class ProvenanceTests(unittest.TestCase):
    def test_reports_pair_but_no_targets(self):
        r=analyze(copy.deepcopy(INPUT),BASE)
        self.assertEqual(r['textual_origins_found'],1)
        self.assertEqual(r['sites'][0]['table_base_candidate'],'0x870b0c')
        self.assertEqual(r['sites'][0]['intervening_transfer_count'],1)
        self.assertEqual(r['sites'][1]['status'],'NOT_TABLE_DISPATCH')
        self.assertFalse(r['control_flow_reaching_definitions_proven'])
        self.assertFalse(r['table_bytes_read'])
        self.assertFalse(r['indirect_targets_resolved'])

    def test_writing_register_between_pair_and_dispatch_rejects(self):
        r=analyze(copy.deepcopy(INPUT),BASE.replace('1008: mov x10, x8','1008: mov x11, x8'))
        self.assertEqual(r['textual_origins_found'],0)
        self.assertEqual(r['sites'][0]['status'],'NO_TEXTUAL_ORIGIN')

    def test_invalid_page_alignment_rejects(self):
        r=analyze(copy.deepcopy(INPUT),BASE.replace('x11, 0x870000','x11, 0x870001'))
        self.assertEqual(r['textual_origins_found'],0)

    def test_missing_matching_adrp_rejects(self):
        r=analyze(copy.deepcopy(INPUT),BASE.replace('1000: adrp x11','1000: mov x11'))
        self.assertEqual(r['textual_origins_found'],0)

    def test_volatile_call_hazard_without_guessing_runtime(self):
        r=analyze(copy.deepcopy(INPUT),BASE.replace('1008: mov x10, x8','1008: bl 0x2000'))
        self.assertTrue(r['sites'][0]['potential_volatile_call_clobber'])
        self.assertEqual(r['textual_origins_with_volatile_call_hazard'],1)
        self.assertFalse(r['sites'][0]['all_paths_reaching_definition_proven'])

    def test_callee_saved_register_call_does_not_mark_volatile(self):
        data=copy.deepcopy(INPUT)
        data['sites'][0]['table_base_register']='x27'
        code=BASE.replace('x11','x27').replace('1008: mov x10, x8','1008: bl 0x2000')
        result=analyze(data,code)
        self.assertEqual(result['textual_origins_found'],1)
        self.assertFalse(result['sites'][0]['potential_volatile_call_clobber'])
        self.assertFalse(result['sites'][0]['all_paths_reaching_definition_proven'])

    def test_duplicate_disassembly_pc_rejected(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            analyze(copy.deepcopy(INPUT),BASE+'101c: br x9\n')

    def test_table_site_disasm_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'not a BR'):
            analyze(copy.deepcopy(INPUT),BASE.replace('101c: br x9','101c: ret'))

    def test_wrong_architecture_rejected(self):
        data=copy.deepcopy(INPUT)
        data['architecture']='ARM32'
        with self.assertRaisesRegex(ValueError,'AArch64'):
            analyze(data,BASE)

if __name__=='__main__':unittest.main()
