"""Fail-closed bounds/segment validation for AArch64 table candidate decoding."""
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from aarch64_table_entries import decode_table, load_segments, inspect

def fixture(offsets=(0,4,8,12),flags=4):
    b=bytearray(0x700)
    b[:7]=b"\x7fELF\x02\x01\x01"
    struct.pack_into("<H",b,18,183)
    struct.pack_into("<Q",b,32,64)
    struct.pack_into("<HH",b,54,56,2)
    struct.pack_into("<IIQQQQQQ",b,64,1,flags,0x100,0x870b00,0,0x100,0x100,0x1000)
    struct.pack_into("<IIQQQQQQ",b,120,1,5,0x300,0x4ea000,0,0x200,0x200,0x1000)
    struct.pack_into("<"+"i"*len(offsets),b,0x180,*offsets)
    return b

class TableEntryTests(unittest.TestCase):
    def test_real_elf_ptload_style_entry_decoding(self):
        b=fixture()
        rows=decode_table(b,load_segments(b),0x870b80,0x4ea000,4,0x4ea000,0x4ea200)
        self.assertEqual([x["candidate_target"] for x in rows],
                         ["0x4ea000","0x4ea004","0x4ea008","0x4ea00c"])

    def test_signed_negative_offsets(self):
        b=fixture((-4,-8,-12,-16))
        rows=decode_table(b,load_segments(b),0x870b80,0x4ea020,4,0x4ea000,0x4ea200)
        self.assertEqual(rows[0]["candidate_target"],"0x4ea01c")

    def test_writable_table_rejected(self):
        b=fixture(flags=6)
        with self.assertRaisesRegex(ValueError,"mapping"):
            decode_table(b,load_segments(b),0x870b80,0x4ea000,4,0x4ea000,0x4ea200)

    def test_out_of_function_target_rejected(self):
        b=fixture((0,4,8,0x400))
        with self.assertRaisesRegex(ValueError,"outside known function"):
            decode_table(b,load_segments(b),0x870b80,0x4ea000,4,0x4ea000,0x4ea200)

    def test_missing_segment_rejected(self):
        b=fixture()
        with self.assertRaisesRegex(ValueError,"mapping"):
            decode_table(b,load_segments(b),0x900000,0x4ea000,4,0x4ea000,0x4ea200)

    def test_too_many_entries_rejected(self):
        b=fixture()
        with self.assertRaisesRegex(ValueError,"bound"):
            decode_table(b,load_segments(b),0x870b80,0x4ea000,65,0x4ea000,0x4ea200)

    def test_unverified_site_stays_unknown(self):
        b=fixture()
        indirect={"architecture":"AArch64","function":"JNI_OnLoad","entry":"0x4ea000",
                  "targets_resolved":False,
                  "sites":[{"pc":"0x4ea040","pattern":"unresolved_indirect_call"}]}
        bounds={"architecture":"AArch64","function":"JNI_OnLoad",
                "indirect_targets_resolved":False,
                "sites":[{"pc":"0x4ea040","local_guard":"unverified"}]}
        r=inspect(b,indirect,bounds,"",0x200)
        self.assertEqual(r["table_sites_with_static_candidates"],0)
        self.assertEqual(r["candidate_entry_count"],0)
        self.assertFalse(r["all_runtime_targets_confirmed"])

if __name__=="__main__":unittest.main()
