"""Conservative ARM64 global data-reference discovery regression tests."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from edgeai_arm64_datarefs import analyze_text, analyze_elf

# Generated from a real Clang AArch64 linked ELF:
# volatile int global_counter = 41;
# __attribute__((noinline)) int tick(int n) { return global_counter + n; }
CLANG_ARM64 = """
0000000000400000 <tick>:
  400000: adrp x8, 0x430000
  400004: ldr w8, [x8, #0x130]
  400008: add w0, w8, w0
  40000c: ret
"""


class Arm64DataReferenceTests(unittest.TestCase):
    def test_real_clang_adrp_ldr_reference(self):
        report = analyze_text(CLANG_ARM64)
        self.assertEqual(report["static_reference_count"], 1)
        self.assertEqual(report["references"][0]["address"], "0x430130")
        self.assertEqual(report["references"][0]["kind"], "load")
        self.assertEqual(report["references"][0]["origin_pc"], "0x400000")

    def test_adrp_add_store_and_register_copy(self):
        asm = """
0000000000400000 <update>:
  400000: adrp x0, 0x430000
  400004: add x0, x0, #0x130
  400008: mov x9, x0
  40000c: str w1, [x9, #0x4]
  400010: ret
"""
        refs = analyze_text(asm)["references"]
        self.assertEqual([(r["kind"], r["address"]) for r in refs],
                         [("computed_address", "0x430130"), ("store", "0x430134")])

    def test_shifted_add_immediate_recovers_page_relative_address(self):
        asm = """
0000000000400000 <shifted>:
  400000: adrp x9, 0x430000
  400004: add x10, x9, #0x2, lsl #12
  400008: ldr w0, [x10, #0x18]
  40000c: ret
"""
        refs = analyze_text(asm)["references"]
        self.assertEqual([(r["kind"], r["address"]) for r in refs],
                         [("computed_address", "0x432000"),
                          ("load", "0x432018")])

    def test_unsupported_shift_and_w_register_add_do_not_invent_refs(self):
        for instruction in ("add x10, x9, #2, lsl #3",
                            "add w10, w9, #2, lsl #12"):
            with self.subTest(instruction=instruction):
                asm = ("""
0000000000400000 <shift_reject>:
  400000: adrp x9, 0x430000
  400004: """ + instruction + """
  400008: ldr w0, [x10, #0x18]
  40000c: ret
""")
                self.assertEqual(analyze_text(asm)["references"], [])

    def test_calls_and_unknown_writes_invalidate_dataflow(self):
        asm = """
0000000000400000 <tick>:
  400000: adrp x8, 0x430000
  400004: bl 0x401000
  400008: ldr w0, [x8, #0x130]
  40000c: adrp x8, 0x430000
  400010: eor x8, x8, x1
  400014: ldr w0, [x8, #0x130]
  400018: ret
"""
        self.assertEqual(analyze_text(asm)["references"], [])

    def test_no_guess_for_dynamic_offset_or_function_merge(self):
        asm = """
0000000000400000 <tick>:
  400000: adrp x8, 0x430000
  400004: ldr w0, [x8, x1]
  400008: b.eq 0x400014
  40000c: ldr w0, [x8, #0x130]
  400010: ret
"""
        self.assertEqual(analyze_text(asm)["references"], [])


    def test_pair_load_clobbers_both_destination_registers(self):
        asm = """
0000000000400000 <pair>:
  400000: adrp x9, 0x430000
  400004: adrp x10, 0x440000
  400008: ldp x9, x10, [x11]
  40000c: ldr w0, [x9, #0x20]
  400010: ldr w1, [x10, #0x20]
  400014: ret
"""
        self.assertEqual(analyze_text(asm)["references"], [])

    def test_writeback_invalidates_base_for_load_store_and_pair(self):
        for writeback in ("str w0, [x9], #8",
                          "ldr w0, [x9, #8]!",
                          "stp x0, x1, [x9, #16]!"):
            with self.subTest(writeback=writeback):
                asm = ("""
0000000000400000 <writeback>:
  400000: adrp x9, 0x430000
  400004: """ + writeback + """
  400008: ldr w0, [x9, #0x30]
  40000c: ret
""")
                self.assertEqual(analyze_text(asm)["references"], [])

    def test_w_register_operations_cannot_preserve_64bit_addresses(self):
        for op in ("mov w9, w9", "add w9, w9, #8"):
            with self.subTest(op=op):
                asm = ("""
0000000000400000 <truncate>:
  400000: adrp x9, 0x430000
  400004: """ + op + """
  400008: ldr w0, [x9, #0x30]
  40000c: ret
""")
                self.assertEqual(analyze_text(asm)["references"], [])

    def test_bitwise_bic_does_not_clear_unrelated_address_register(self):
        asm = """
0000000000400000 <bitwise>:
  400000: adrp x9, 0x430000
  400004: bic x0, x0, x1
  400008: ldr w0, [x9, #0x30]
  40000c: ret
"""
        refs = analyze_text(asm)["references"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["address"], "0x430030")

    def test_literal_ldr_and_ldrsw_recover_direct_pc_relative_loads(self):
        asm = """
0000000000400000 <literals>:
  400000: ldr x0, 0x401000 <constant_table>
  400004: ldrsw x1, 0x401004
  400008: ldr w2, 0x401008 <constant_table+0x8>
  40000c: ret
"""
        refs = analyze_text(asm)["references"]
        self.assertEqual([r["address"] for r in refs],
                         ["0x401000", "0x401004", "0x401008"])
        self.assertEqual([r["opcode"] for r in refs],
                         ["ldr", "ldrsw", "ldr"])
        self.assertTrue(all(r["kind"] == "load" and
                            r["addressing"] == "literal" for r in refs))

    def test_linked_clang_arm64_literal_fixture(self):
        # Independently assembled with Clang and linked as AArch64 ET_DYN.
        # LLVM objdump emits literal targets with function+offset comments.
        asm = """
0000000000010228 <literal_test>:
   10228:       ldr x0, 0x10238 <literal_test+0x10>
   1022c:       ldrsw x1, 0x10240 <literal_test+0x18>
   10230:       ret
   10234:       nop
   10238: f0 de bc 9a   .word 0x9abcdef0
   1023c: 78 56 34 12   .word 0x12345678
   10240: 2a 00 00 00   .word 0x0000002a
"""
        refs = analyze_text(asm)["references"]
        self.assertEqual([(r["opcode"], r["address"]) for r in refs],
                         [("ldr", "0x10238"), ("ldrsw", "0x10240")])

    def test_literal_load_clobbers_previous_address_provenance(self):
        asm = """
0000000000400000 <literal_clobber>:
  400000: adrp x8, 0x430000
  400004: ldr x8, 0x401000
  400008: ldr w0, [x8, #0x30]
  40000c: ret
"""
        refs = analyze_text(asm)["references"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["address"], "0x401000")

    def test_nonliteral_ldr_keeps_existing_memory_semantics(self):
        asm = """
0000000000400000 <memory>:
  400000: adrp x8, 0x430000
  400004: ldrsw x0, [x8, #0x24]
  400008: ret
"""
        refs = analyze_text(asm)["references"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["address"], "0x430024")
        self.assertNotIn("addressing", refs[0])

    def test_relocatable_object_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.o"
            header = bytearray(20)
            header[:6] = bytes([127, 69, 76, 70, 2, 1])
            header[16:18] = (1).to_bytes(2, "little")
            header[18:20] = (183).to_bytes(2, "little")
            path.write_bytes(header)
            with self.assertRaisesRegex(ValueError, "requires linked ARM64"):
                analyze_elf(path)


if __name__ == "__main__":
    unittest.main()
