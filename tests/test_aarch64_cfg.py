"""Reject unsound CFG inputs and test an authentic compiled AArch64 fixture."""
import sys
import tempfile
import shutil
import subprocess
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_cfg import build_graph
from aarch64_branch_map import analyze


def graph_input():
    return {
        "architecture":"AArch64", "function":"test_fn", "entry":"0x1000",
        "size_bytes":36,"decoded_control_transfers":5,"sample_truncated":False,
        "control_transfer_candidates":[
            {"pc":"0x1004","kind":"CBZ","target":"0x1018"},
            {"pc":"0x100c","kind":"BL","target":"0x3000"},
            {"pc":"0x1014","kind":"B","target":"0x1004"},
            {"pc":"0x1018","kind":"RET","target":None},
            {"pc":"0x1020","kind":"BR","target":None}
        ]
    }


class Arm64GraphTests(unittest.TestCase):
    def test_backwards_branches_external_calls_and_unknown_jumps(self):
        r=build_graph(graph_input())
        self.assertEqual(r["backward_edge_candidates"],1)
        self.assertEqual(r["edge_kind_counts"]["direct_call_site"],1)
        self.assertEqual(r["edge_kind_counts"]["indirect_jump_unresolved"],1)
        self.assertTrue(any(x["kind"]=="taken_candidate" and x["to"]=="0x1018" for x in r["edges"]))
        self.assertFalse(r["reachability_proven"])
        self.assertFalse(r["code_executed"])
        self.assertGreaterEqual(r["candidate_entry_reachable_blocks"],4)

    def test_truncated_scan_refused(self):
        scan=graph_input()
        scan["sample_truncated"]=True
        with self.assertRaisesRegex(ValueError,"complete"):
            build_graph(scan)

    def test_duplicate_pc_refused(self):
        scan=graph_input()
        scan["control_transfer_candidates"][1]["pc"]="0x1004"
        with self.assertRaisesRegex(ValueError,"duplicate"):
            build_graph(scan)

    def test_wrong_architecture_refused(self):
        scan=graph_input()
        scan["architecture"]="ARM32"
        with self.assertRaisesRegex(ValueError,"AArch64"):
            build_graph(scan)

    def test_real_compiled_aarch64_elf(self):
        if not shutil.which("clang") or not shutil.which("ld.lld"):
            self.skipTest("clang/lld unavailable")
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)
            (path/"f.c").write_text(
                "__attribute__((noinline)) int helper(int n){return n*2;}\n"
                "__attribute__((visibility(\"default\"))) int JNI_OnLoad(int n){"
                " if(n<0)return -1; return helper(n)+3; }\n")
            lib=path/"f.so"
            subprocess.run(["clang","--target=aarch64-linux-gnu","-fuse-ld=lld",
                "-O0","-shared","-nostdlib","-o",str(lib),str(path/"f.c")],
                capture_output=True,check=True)
            scan=analyze(lib.read_bytes(),"JNI_OnLoad",max_results=1000)
            result=build_graph(scan)
            self.assertGreater(result["block_count"],1)
            self.assertEqual(result["entry"],scan["entry"])
            self.assertFalse(result["code_executed"])


if __name__=="__main__":unittest.main()
