"""Regression tests for conservative AArch64 local dispatch guard inference."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_dispatch_bounds import analyze

BASE={"function":"fixture","architecture":"AArch64","targets_resolved":False,
      "sites":[{"pc":"0x1020",
       "pattern":"pc_relative_indexed_table_dispatch_candidate",
       "index_register":"x12","table_base_register":"x17",
       "evidence_pcs":["0x1014","0x1018","0x101c","0x1020"]},
       {"pc":"0x1050","pattern":"unresolved_indirect_call"}]}
CODE="\n".join((
    "  100c: cmp w12, #0x7",
    "  1010: b.hi 0x1100",
    "  1014: adr x14, 0x1014",
    "  1018: ldrsw x15, [x17, x12, lsl #2]",
    "  101c: add x14, x14, x15",
    "  1020: br x14",
    "  1050: blr x8",
))+"\n"

class GuardTests(unittest.TestCase):
    def test_adjacent_unsigned_guard(self):
        r=analyze(copy.deepcopy(BASE),CODE)
        self.assertEqual(r["locally_guarded_table_dispatch_sites"],1)
        self.assertEqual(r["sites"][0]["local_candidate_table_entries"],8)
        self.assertFalse(r["sites"][0]["all_incoming_paths_guarded"])
        self.assertFalse(r["indirect_targets_resolved"])
        self.assertFalse(r["original_game_executed"])

    def test_adrp_add_guard_with_valid_table_base(self):
        b=copy.deepcopy(BASE)
        b["sites"][0]["pc"]="0x1028"
        b["sites"][0]["evidence_pcs"]=["0x101c","0x1020","0x1024","0x1028"]
        text=CODE.replace("1014: adr", "1014: adrp x17, 0x4000\n  1018: add x17, x17, #0x120\n  101c: adr").replace(
            "1018: ldrsw", "1020: ldrsw").replace(
            "101c: add x14","1024: add x14").replace("1020: br x14","1028: br x14")
        r=analyze(b,text)
        self.assertEqual(r["locally_guarded_table_dispatch_sites"],1)

    def test_unconditional_branch_not_a_guard(self):
        r=analyze(copy.deepcopy(BASE),CODE.replace("b.hi 0x1100","b 0x1014"))
        self.assertEqual(r["locally_guarded_table_dispatch_sites"],0)

    def test_wrong_index_register_is_not_guarded(self):
        r=analyze(copy.deepcopy(BASE),CODE.replace("cmp w12","cmp w8"))
        self.assertEqual(r["locally_guarded_table_dispatch_sites"],0)

    def test_guard_to_inside_dispatch_refused(self):
        r=analyze(copy.deepcopy(BASE),CODE.replace("b.hi 0x1100","b.hi 0x1018"))
        self.assertEqual(r["locally_guarded_table_dispatch_sites"],0)

    def test_missing_adrp_for_base_materialization(self):
        b=copy.deepcopy(BASE)
        b["sites"][0]["pc"]="0x1028"
        b["sites"][0]["evidence_pcs"]=["0x101c","0x1020","0x1024","0x1028"]
        text=CODE.replace("1014: adr","1014: nop\n  1018: add x17, x17, #0x120\n  101c: adr").replace(
            "1018: ldrsw","1020: ldrsw").replace("101c: add x14","1024: add x14").replace("1020: br x14","1028: br x14")
        r=analyze(b,text)
        self.assertEqual(r["locally_guarded_table_dispatch_sites"],0)

    def test_reject_pre_resolved_targets(self):
        b=copy.deepcopy(BASE)
        b["targets_resolved"]=True
        with self.assertRaisesRegex(ValueError,"unresolved"):
            analyze(b,CODE)

if __name__=="__main__":unittest.main()
