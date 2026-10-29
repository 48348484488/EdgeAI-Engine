#!/usr/bin/env python3
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
try:
    from edgeai_unity_buildpart_decode import report_from_bytes, decode
except ModuleNotFoundError:
    from unity_buildpart_decode import report_from_bytes, decode

def row(n,typ,icon="buildpart/dj"):
    q=bytearray()
    def i(x):q.extend(struct.pack("<i",x))
    def b(x):q.extend(struct.pack("B",int(x)))
    def s(x):
        t=x.encode("utf8");i(len(t));q.extend(t)
    i(n);i(typ);i(0);s("Base "+str(n))
    i(1);i(1);i(n);i(n+1);s(icon)
    b(True);s("part/diji_lv1.ab");b(True);b(False)
    for x in (0,10,20,30):i(x)
    b(False);s("1|4")
    for x in (101,50,100,20):i(x)
    for x in (50,51,52):i(x)
    i(0);i(90);b(True)
    i(1);i(102);i(20)
    b(False);b(False)
    q.extend(bytes(23))  # opaque version-dependent trailing record extension
    return bytes(q)

class TestBuildPartDecode(unittest.TestCase):
    def setUp(self):
        self.blob=b"".join(row(i+1,2+(i%7)) for i in range(14))
    def test_exact_fields_and_order(self):
        result=report_from_bytes(self.blob)
        self.assertEqual(result["record_count"],14)
        self.assertEqual(result["basic_level1_count"],14)
        r=result["all_records"][0]
        self.assertEqual((r["type"],r["lv"],r["OnceAngle"]),(2,1,90))
        self.assertEqual(r["materialInfo"]["needNum"],50)
        self.assertEqual(r["btns"],[1,4])
        self.assertEqual(r["model"],"part/diji_lv1.ab")
        self.assertEqual(result["groups"]["foundation"]["count"],2)
    def test_truncated_rejected(self):
        with self.assertRaises(ValueError): decode(self.blob[:-3])
    def test_bad_string_length_rejected(self):
        tampered=bytearray(self.blob)
        tampered[12:16]=struct.pack("<i",2147483647)
        with self.assertRaises(ValueError):decode(tampered)
    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            report_from_bytes(b"".join(row(1,2) for _ in range(14)))
    def test_sprite_mapping_exact_only(self):
        data=report_from_bytes(self.blob,[{"bundle":"assets/icon/buildpart.ab",
                       "icons":[{"name":"dj","id":"-42","file":"p.png"}]}])
        x=data["groups"]["foundation"]["items"][0]
        self.assertEqual(x["icon_resolution"],"unique")
        self.assertEqual(x["verified_icon_candidates"][0]["path_id"],"-42")
    def test_ambiguous_sprite_name_rejected_as_unique(self):
        icons=[{"bundle":"assets/icon/buildpart.ab", "icons":[
                {"name":"dj","id":"1","file":"a.png"},
                {"name":"dj","id":"2","file":"b.png"}]}]
        self.assertEqual(report_from_bytes(self.blob,icons)["all_records"][0]["icon_resolution"],
                         "ambiguous")
if __name__=="__main__":unittest.main()
