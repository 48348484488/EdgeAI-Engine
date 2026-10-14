"""Forensic snapshot is deliberately separate from CFG and runtime claims."""
import copy
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_forensic_tables import inspect

def example():
    elf=bytearray(0x700)
    elf[:7]=b"\x7fELF\x02\x01\x01"
    struct.pack_into("<H",elf,18,183)
    struct.pack_into("<Q",elf,32,64)
    struct.pack_into("<HH",elf,54,56,2)
    struct.pack_into("<IIQQQQQQ",elf,64,1,4,0x100,0x870b00,0,0x100,0x100,0x1000)
    struct.pack_into("<IIQQQQQQ",elf,120,1,5,0x300,0x4ea000,0,0x200,0x200,0x1000)
    off=[0x18,0x28,0x38,0x48,0x18,0x28,0x38,0x48]
    struct.pack_into("<8i",elf,0x160,*off)
    indir={"architecture":"AArch64","function":"JNI_OnLoad","entry":"0x4ea000","targets_resolved":False,
        "sites":[{"pc":"0x4ea134","pattern":"pc_relative_indexed_table_dispatch_candidate",
                  "table_base_register":"x0","index_register":"x12"}]}
    bounds={"architecture":"AArch64","function":"JNI_OnLoad","indirect_targets_resolved":False,
        "sites":[{"pc":"0x4ea134","local_guard":"unsigned_index_upper_bound_candidate",
                  "index_register":"x12","local_unsigned_index_max_inclusive":7,
                  "local_candidate_table_entries":8,
                  "guard_compare_pc":"0x4ea120","guard_branch_pc":"0x4ea124"}]}
    prov={"architecture":"AArch64","function":"JNI_OnLoad","indirect_targets_resolved":False,
        "sites":[{"pc":"0x4ea134","status":"TEXTUAL_ADRP_ADD_CANDIDATE",
                  "table_base_register":"x0","table_base_candidate":"0x870b60",
                  "adrp_pc":"0x4ea024","add_pc":"0x4ea03c",
                  "intervening_transfer_count":1}]}
    graph={"architecture":"AArch64","function":"JNI_OnLoad","entry":"0x4ea000","symbol_size_bytes":0x200,
           "code_executed":False,"blocks":[
               {"start":hex(x),"last_instruction":hex(x+4),
                "last_control_transfer":"BR" if x==0x4ea130 else "RET"}
               for x in (0x4ea130,0x4ea140,0x4ea150,0x4ea160,0x4ea170)]}
    graph["blocks"][0]["last_instruction"]="0x4ea134"
    code={0x4ea024:"adrp x0, 0x870000",0x4ea03c:"add x0, x0, #0xb60",
          0x4ea120:"cmp w12, #0x7",0x4ea124:"b.hi 0x4ea190",
          0x4ea128:"adr x13, 0x4ea128",0x4ea12c:"ldrsw x14, [x0, x12, lsl #2]",
          0x4ea130:"add x13, x13, x14",0x4ea134:"br x13"}
    for at in range(0x4ea028,0x4ea120,4):
        if at not in code:code[at]="nop"
    source="\n".join(" %x: %s"%(pc,op) for pc,op in sorted(code.items()))
    return elf,indir,bounds,prov,graph,source

class ForensicTests(unittest.TestCase):
    def test_static_eight_entries_without_graph_promotion(self):
        params=example()
        r=inspect(*params[:5],params[5],0x200)
        self.assertEqual(r["forensic_tables"],1)
        self.assertEqual(r["forensic_entries"],8)
        self.assertFalse(r["cfg_modified"])
        self.assertFalse(r["runtime_paths_proven"])
        self.assertFalse(r["sites"][0]["cfg_edge_promotion_authorized"])
        self.assertFalse(r["sites"][0]["runtime_reaching_definition_proven"])

    def test_call_clobber_rejected_for_x0(self):
        params=list(example())
        params[5]=params[5].replace("4ea044: nop","4ea044: bl 0x600000")
        r=inspect(*params[:5],params[5],0x200)
        self.assertEqual(r["forensic_tables"],0)
        self.assertEqual(r["sites"][0]["reason"],"possible_base_clobber_or_incomplete_instruction_stream")

    def test_register_write_rejected(self):
        params=list(example())
        params[5]=params[5].replace("4ea044: nop","4ea044: mov x0, x5")
        self.assertEqual(inspect(*params[:5],params[5],0x200)["forensic_tables"],0)

    def test_non_cfg_leader_rejected(self):
        params=list(example())
        params[4]["blocks"].pop()
        self.assertEqual(inspect(*params[:5],params[5],0x200)["forensic_tables"],0)

    def test_bad_provenance_base_rejected(self):
        params=list(example())
        params[3]["sites"][0]["table_base_candidate"]="0x870b70"
        with self.assertRaisesRegex(ValueError,"reproducible"):
            inspect(*params[:5],params[5],0x200)

    def test_incorrect_guard_rejected(self):
        params=list(example())
        params[5]=params[5].replace("cmp w12","cmp w13")
        with self.assertRaisesRegex(ValueError,"guard index mismatch"):
            inspect(*params[:5],params[5],0x200)

    def test_wrong_table_permission_rejected(self):
        params=list(example())
        struct.pack_into("<I",params[0],68,6)
        self.assertEqual(inspect(*params[:5],params[5],0x200)["forensic_tables"],0)

if __name__=="__main__":unittest.main()
