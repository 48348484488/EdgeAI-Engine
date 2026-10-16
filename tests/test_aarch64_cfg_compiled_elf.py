"""Compiler-backed AArch64 disassembly regression (no target binary execution)."""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from aarch64_cfg_provenance import analyze

SOURCE = """
.text
.global dispatch_test
.type dispatch_test, %function
dispatch_test:
    adrp x11, dispatch_table
    cbz x0, alternate
    nop
    b merge
alternate:
    nop
merge:
    add x11, x11, :lo12:dispatch_table
    adr x9, jump_origin
    ldrsw x10, [x11, x8, lsl #2]
    add x9, x9, x10
    br x9
jump_origin:
    ret
.size dispatch_test, . - dispatch_test
.section .rodata
.p2align 2
dispatch_table:
.word jump_origin - jump_origin
"""


class CompilerBackedTests(unittest.TestCase):
    @unittest.skipUnless(all(shutil.which(x) for x in ("clang", "ld.lld", "llvm-objdump")),
                         "requires Clang, LLD and llvm-objdump")
    def test_real_arm64_elf_disassembly_static_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asm = root / "dispatch.S"
            obj = root / "dispatch.o"
            elf = root / "dispatch.elf"
            asm.write_text(SOURCE)
            subprocess.run(["clang", "--target=aarch64-none-elf", "-c",
                            str(asm), "-o", str(obj)], check=True, capture_output=True)
            subprocess.run(["clang", "--target=aarch64-none-elf",
                            "-fuse-ld=lld", "-nostdlib", "-Wl,-Ttext=0x1000",
                            "-Wl,-e,dispatch_test", str(obj), "-o", str(elf)],
                           check=True, capture_output=True)
            disasm = subprocess.check_output(
                ["llvm-objdump", "--no-show-raw-insn", "-d", str(elf)],
                text=True)
        spans = [(0x1000, 0x1008, "CBZ"),
                 (0x1008, 0x1010, "B"),
                 (0x1010, 0x1014, None),
                 (0x1014, 0x1028, "BR"),
                 (0x1028, 0x102c, "RET")]
        blocks = [dict(start=hex(a), end_exclusive=hex(b),
                       size_bytes=b-a, last_instruction=hex(b-4),
                       last_control_transfer=kind) for a, b, kind in spans]
        edge_rows = [(0x1000, 0x1010, "taken_candidate"),
                     (0x1000, 0x1008, "not_taken_candidate"),
                     (0x1008, 0x1014, "unconditional"),
                     (0x1010, 0x1014, "linear_candidate"),
                     (0x1014, None, "indirect_jump_unresolved"),
                     (0x1028, None, "return_candidate")]
        edges = [dict(**{"from": hex(src)}, to=hex(dst) if dst else None,
                      kind=kind, target_in_symbol=dst is not None)
                 for src, dst, kind in edge_rows]
        graph = dict(architecture="AArch64", function="dispatch_test",
                     entry="0x1000", symbol_size_bytes=0x2c,
                     code_executed=False, blocks=blocks,
                     block_count=len(blocks), edges=edges, edge_count=len(edges))
        indirect = dict(architecture="AArch64", function="dispatch_test",
                        entry="0x1000", targets_resolved=False,
                        indirect_site_count=1,
                        sites=[dict(pc="0x1024",
                                    pattern="pc_relative_indexed_table_dispatch_candidate",
                                    table_base_register="x11", index_register="x8")])
        result = analyze(graph, indirect, disasm)
        adr = re.search(r"1000:\s+adrp\s+x11,\s+(0x[0-9a-f]+)", disasm)
        add = re.search(r"1014:\s+add\s+x11,\s+x11,\s+#(0x[0-9a-f]+)", disasm)
        self.assertIsNotNone(adr)
        self.assertIsNotNone(add)
        expected = int(adr[1], 16) + int(add[1], 16)
        self.assertEqual(result["static_cfg_base_candidates"], 1)
        self.assertEqual(int(result["sites"][0]["table_base_candidate"], 16), expected)
        self.assertFalse(result["code_executed"])
        self.assertFalse(result["runtime_control_flow_proven"])


if __name__ == "__main__":
    unittest.main()
