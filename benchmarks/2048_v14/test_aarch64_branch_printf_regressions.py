"""Strict source-blind AArch64 dynamic printf and linked loop regressions.

The original C in oracle_POST_GENERATION_ONLY/ is consulted only after
regenerating C++ code solely from the stripped ELF + accepted ABI contracts.
"""
import hashlib, json, os, shutil, struct, subprocess, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from aarch64_branch_printf_lifter import (_bounded_frame, _string_roles,
                                          discover as printer_discover, lift as printer_lift)
from aarch64_print_loop_caller_lifter import (discover as caller_discover, lift as caller_lift)
from aarch64_leaf_lifter import parse_instructions
from aarch64_printf_lifter import load_rodata
from aarch64_stripped_discovery import load_text

ROOT=Path(__file__).resolve().parents[1]
ELF=ROOT/'bin/2048-arm64-stripped.elf'
COVERAGE=ROOT/'batch_v7/coverage.json'
EXPECT='a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b'


class BranchAndLoopStrictTests(unittest.TestCase):
    def test_elf_is_stripped_sha_pinned(self):
        self.assertEqual(hashlib.sha256(ELF.read_bytes()).hexdigest(), EXPECT)

    def test_printer_entry_discovered_without_original_game_names(self):
        found,rejected=printer_discover(ELF,COVERAGE)
        self.assertEqual(len(found),1)
        addr,src,meta=found[0]
        self.assertEqual(addr,0x401004)
        self.assertEqual(meta['instructions_translated'],114)
        self.assertEqual(meta['printf_call_sites'],14)
        self.assertEqual(meta['internal_scalar_call_sites'],1)
        self.assertFalse(meta['symbols_used']);self.assertFalse(meta['source_read'])
        self.assertNotIn('print_cell',src)
        self.assertEqual(len(rejected),26)

    def test_printer_linked_callback_rejects_no_contract(self):
        with self.assertRaisesRegex(ValueError,'no proven scalar'):
            printer_lift(ELF,0x401004,0x4011cc,set())

    def test_printer_rejects_unsupported_bl(self):
        with self.assertRaisesRegex(ValueError,'unsupported BL target'):
            printer_lift(ELF,0x401004,0x4011cc,{0x401404})

    def test_printer_has_no_game_addresses_embedded_in_generator(self):
        source=(ROOT/'analysis/aarch64_branch_printf_lifter.py').read_text()
        for s in ('_print_cell','src/draw.c','0x401004','0x400f58', 'You win !'):
            with self.subTest(s=s):self.assertNotIn(s,source)

    def test_caller_has_no_original_game_names_or_addresses(self):
        source=(ROOT/'analysis/aarch64_print_loop_caller_lifter.py').read_text()
        for s in ('print_board','src/draw.c','0x401404','0x401004'):
            with self.subTest(s=s):self.assertNotIn(s,source)

    def test_detects_complete_callgraph_from_binary(self):
        matches,_=printer_discover(ELF,COVERAGE)
        # Contract is extracted from generated code only, no source oracle.
        with tempfile.TemporaryDirectory() as d:
            tmp=Path(d)/'printer.json'
            tmp.write_text(json.dumps({'matches':[m[2] for m in matches]})+'\n')
            callers,rejected=caller_discover(ELF,COVERAGE,tmp)
        self.assertEqual(len(callers),1)
        self.assertEqual(callers[0][0],0x401404)
        self.assertEqual(callers[0][2]['instructions_translated'],32)
        self.assertEqual(callers[0][2]['indexed_memory_read_sites'],1)
        self.assertEqual(callers[0][2]['board_region_bytes'],64)
        self.assertEqual(len(rejected),26)

    def test_rejects_missing_callee(self):
        with self.assertRaisesRegex(ValueError,'missing printer'):
            caller_lift(ELF,0x401404,0x401484,set())

    def test_rejects_bad_memory_opcode_candidate(self):
        with self.assertRaisesRegex(ValueError,'unsupported opcode'):
            caller_lift(ELF,0x4012d0,0x401404,{0x401004})

    def test_rejects_unbalanced_stack_frame(self):
        rows=parse_instructions(ELF,0x401004,0x4011cc)
        bad=list(rows)
        p,op,operand=bad[0]
        bad[0]=(p,op,operand.replace('0x40','0x50'))
        with self.assertRaisesRegex(ValueError,'unbalanced'):
            _bounded_frame(bad)

    def test_code_changes_when_elf_literal_is_mutated(self):
        data=ELF.read_bytes()
        needle='╭────────╮\n'.encode()
        self.assertEqual(data.count(needle),1)
        altered=data.replace(needle,'╭────╳───╮\n'.encode())
        self.assertEqual(len(altered),len(data))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'changed.elf';p.write_bytes(altered)
            orig=printer_lift(ELF,0x401004,0x4011cc,{0x400f58})[0]
            mutant=printer_lift(p,0x401004,0x4011cc,{0x400f58})[0]
            self.assertNotEqual(orig,mutant)

    def test_cbz_mutation_is_translated_instead_of_rejected(self):
        info=load_text(ELF)
        rows=parse_instructions(ELF,0x401004,0x4011cc)
        pc=next(pc for pc,op,_ in rows if op=='cbnz')
        data=bytearray(ELF.read_bytes())
        offset=data.find(info['text'])
        self.assertGreaterEqual(offset,0)
        at=offset+pc-info['text_address']
        opcode,=struct.unpack_from('<I',data,at)
        self.assertEqual(opcode&0x7f000000,0x35000000)
        struct.pack_into('<I',data,at,opcode&~(1<<24))
        with tempfile.TemporaryDirectory() as d:
            changed=Path(d)/'cbz.elf';changed.write_bytes(data)
            original=printer_lift(ELF,0x401004,0x4011cc,{0x400f58})[0]
            mutated=printer_lift(changed,0x401004,0x4011cc,{0x400f58})[0]
            self.assertNotEqual(original,mutated)
            self.assertIn('if (uint32_t(r[0])==0)',mutated)

    def test_invalid_elf_provenance_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong.elf';data=bytearray(ELF.read_bytes());data[-1]^=1;p.write_bytes(data)
            with self.assertRaisesRegex(ValueError,'sha'):
                printer_discover(p,COVERAGE)

    @unittest.skipUnless(shutil.which('gcc') and shutil.which('g++'),'requires native C/C++')
    def test_compiled_new_cpp_matches_independent_postgen_c_on_edge_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            temp=Path(d)
            matches,_=printer_discover(ELF,COVERAGE)
            entry,cpp,ev=matches[0]
            (temp/'printer.cpp').write_text(cpp)
            (temp/'driver.cpp').write_text((ROOT/'print_v14/generated_driver.cpp').read_text())
            subprocess.run(['g++','-O2','-std=c++17',str(temp/'driver.cpp'),
                str(temp/'printer.cpp'),str(ROOT/'batch_v7/candidate_400f58.cpp'),'-o',str(temp/'candidate')],check=True,capture_output=True)
            subprocess.run(['gcc','-O2','-std=c11',str(ROOT/'oracle_POST_GENERATION_ONLY/original_print_cell.c'),
                '-o',str(temp/'oracle')],check=True,capture_output=True)
            for value,row,col in [(0,0,0),(2,3,3),(2048,1,2),(9,0,3),(10,2,1),
                                  (99,3,0),(100,1,1),(999,2,2),(1000,3,1),(9999,0,0)]:
                args=[str(value),str(row),str(col)]
                self.assertEqual(subprocess.check_output([str(temp/'candidate'),*args]),
                                 subprocess.check_output([str(temp/'oracle'),*args]))

    @unittest.skipUnless(shutil.which('gcc') and shutil.which('g++'),'requires native C/C++')
    def test_negative_control_wrong_machine_branch_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            t=Path(d)
            src=printer_discover(ELF,COVERAGE)[0][0][1]
            old='if (uint32_t(r[0])!=0) goto pc_401140;'
            new='if (uint32_t(r[0])==0) goto pc_401140;'
            self.assertEqual(src.count(old),1)
            (t/'mutant.cpp').write_text(src.replace(old,new))
            subprocess.run(['g++','-O2','-std=c++17',
                str(ROOT/'print_v14/generated_driver.cpp'),str(t/'mutant.cpp'),
                str(ROOT/'batch_v7/candidate_400f58.cpp'),'-o',str(t/'mutant')],
                check=True,capture_output=True)
            args=['2','1','1']
            wrong=subprocess.check_output([str(t/'mutant'),*args])
            subprocess.run(['gcc','-O2','-std=c11',
                str(ROOT/'oracle_POST_GENERATION_ONLY/original_print_cell.c'),
                '-o',str(t/'original')],check=True,capture_output=True)
            expected=subprocess.check_output([str(t/'original'),*args])
            self.assertNotEqual(wrong,expected)

    @unittest.skipUnless(shutil.which('gcc') and shutil.which('g++'),'requires native C/C++')
    def test_compiled_full_board_caller_matches_independent_postgen_c(self):
        with tempfile.TemporaryDirectory() as d:
            t=Path(d)
            found,_=printer_discover(ELF,COVERAGE)
            (t/'cell.cpp').write_text(found[0][1])
            (t/'printer.json').write_text(json.dumps({'matches':[found[0][2]]}))
            calls,_=caller_discover(ELF,COVERAGE,t/'printer.json')
            (t/'board.cpp').write_text(calls[0][1])
            subprocess.run(['g++','-O2','-std=c++17',str(ROOT/'print_v14/generated_board_driver.cpp'),
                str(t/'cell.cpp'),str(t/'board.cpp'),str(ROOT/'batch_v7/candidate_400f58.cpp'),
                '-o',str(t/'candidate')],check=True,capture_output=True)
            subprocess.run(['gcc','-O2','-std=c11',str(ROOT/'oracle_POST_GENERATION_ONLY/original_print_board.c'),
                '-o',str(t/'oracle')],check=True,capture_output=True)
            for values in ([0]*16,[2]*16,[2048]*16,list(range(16)),[9999]*16):
                args=list(map(str,values))
                self.assertEqual(subprocess.check_output([str(t/'candidate'),*args]),
                                 subprocess.check_output([str(t/'oracle'),*args]))

if __name__=='__main__':unittest.main()