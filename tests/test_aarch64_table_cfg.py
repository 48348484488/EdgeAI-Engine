"""Regression tests: candidate indirect table targets only at CFG block boundaries."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_table_cfg import enrich


def fixture():
    graph={
        "architecture":"AArch64","function":"JNI_OnLoad","entry":"0x1000",
        "code_executed":False,"block_count":3,"candidate_entry_reachable_blocks":1,
        "blocks":[
            {"start":"0x1000","last_control_transfer":"BR","last_instruction":"0x100c"},
            {"start":"0x1010","last_control_transfer":"RET","last_instruction":"0x1014"},
            {"start":"0x1018","last_control_transfer":"RET","last_instruction":"0x101c"},
        ],
        "edges":[{"from":"0x1000","to":None,"kind":"indirect_jump_unresolved",
                  "target_in_symbol":False}],
    }
    report={
        "architecture":"AArch64","function":"JNI_OnLoad",
        "status":"BOUNDED_AARCH64_STATIC_JUMP_TABLE_AUDIT",
        "game_executed":False,"table_sites_with_static_candidates":1,
        "candidate_entry_count":3,
        "sites":[{
            "pc":"0x100c","status":"STATIC_CANDIDATES",
            "locally_bounded_entry_count":3,
            "candidate_entries":[
                {"index":0,"candidate_target":"0x1010"},
                {"index":1,"candidate_target":"0x1018"},
                {"index":2,"candidate_target":"0x1010"}
            ],
        }],
    }
    return graph,report


class EnrichedGraphTests(unittest.TestCase):
    def test_distinct_edges_and_duplicate_index_targets(self):
        g,r=fixture()
        out=enrich(g,r)
        self.assertEqual(out["guarded_table_entry_count"],3)
        self.assertEqual(out["guarded_table_distinct_edge_count"],2)
        self.assertEqual(out["augmented_candidate_edge_count"],3)
        self.assertEqual(out["entry_reachable_under_augmented_partial_model"],3)
        self.assertEqual(out["candidate_entry_reachable_blocks"],1)
        self.assertEqual(out["bounded_table_candidate_edges"][0]["indexes"],[0,2])
        self.assertFalse(out["runtime_reachability_proven"])
        self.assertEqual(g["edges"][0]["kind"],"indirect_jump_unresolved")

    def test_missing_index_rejected(self):
        g,r=fixture()
        r["sites"][0]["candidate_entries"][1]["index"]=2
        with self.assertRaisesRegex(ValueError,"duplicate"): enrich(g,r)

    def test_unmapped_target_rejected(self):
        g,r=fixture()
        r["sites"][0]["candidate_entries"][0]["candidate_target"]="0x1020"
        with self.assertRaisesRegex(ValueError,"boundary"):enrich(g,r)

    def test_dispatch_must_end_br(self):
        g,r=fixture()
        g["blocks"][0]["last_control_transfer"]="BLR"
        with self.assertRaisesRegex(ValueError,"unresolved BR"):enrich(g,r)

    def test_wrong_function_rejected(self):
        g,r=fixture()
        r["function"]="UnitySendMessage"
        with self.assertRaisesRegex(ValueError,"identity"):enrich(g,r)

    def test_reject_over_limit(self):
        g,r=fixture()
        r["sites"][0]["locally_bounded_entry_count"]=65
        with self.assertRaisesRegex(ValueError,"oversized"):enrich(g,r)


if __name__=="__main__":unittest.main()
