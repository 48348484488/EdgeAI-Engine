#!/usr/bin/env python3
"""EdgeAI: decode ORIGINAL Unity cfg.BuildPart.oc, preserving exact order.

The layout is derived from decompiled cfg.BuildPart(Octets), MaterialInfo,
FixBuildMaterialInfo and Share.Octets classes. No guessing at icon filenames.
Offline, stdlib-only, bounded reads. Never executes the Unity game.
"""
import argparse
import collections
import hashlib
import json
import shutil
import struct
import tempfile
import zipfile
from pathlib import Path

SOURCE_PATH = "assets/cfg/cfg.BuildPart.oc"
APK_NAME = "com.herogame.gplay.survival.lite.apk"
CATEGORIES = {2:"foundation",3:"wall",4:"stair",5:"door",
              6:"window",7:"obstacle",8:"floor"}

class Octets:
    def __init__(self, payload):
        self.data = memoryview(payload)
        self.off = 0
    def pop(self, fmt):
        n=struct.calcsize(fmt)
        if self.off+n>len(self.data):
            raise ValueError("cfg.BuildPart.oc truncated at " + str(self.off))
        v=struct.unpack_from("<"+fmt,self.data,self.off)[0]
        self.off+=n
        return v
    def integer(self): return self.pop("i")
    def boolean(self):
        v=self.pop("B")
        if v not in (0,1): raise ValueError("Invalid Unity boolean at "+str(self.off-1))
        return bool(v)
    def string(self):
        count=self.integer()
        if not 0<=count<=1024*1024 or self.off+count>len(self.data):
            raise ValueError("Bad Unity string length at "+str(self.off-4))
        result=self.data[self.off:self.off+count].tobytes().decode("utf-8")
        self.off+=count
        return result

def decode(payload):
    reader=Octets(payload)
    rows=[]
    while reader.off<len(reader.data):
        start=reader.off
        r={}
        for name in ("id","type","functionType"):
            r[name]=reader.integer()
        r["name"]=reader.string()
        for name in ("lv","lv1Id","nextId"):
            r[name]=reader.integer()
        r["icon"]=reader.string()
        r["canUpgrade"]=reader.boolean()
        r["model"]=reader.string()
        r["basic"]=reader.boolean()
        for name in ("needSupportValue","destoryEffectId",
                     "buildEffectId","upLvEffectId"):
            r[name]=reader.integer()
        r["needCheck"]=reader.boolean()
        r["btns"]=[int(x) for x in reader.string().split("|") if x.lstrip("-").isdigit()]
        r["otherPlayerbtns"]=[int(x) for x in reader.string().split("|") if x.lstrip("-").isdigit()]
        r["materialInfo"]={k:reader.integer() for k in
                           ("itemId","needNum","hp","returnNum")}
        for name in ("buildSoundId","destorySoundId","upSoundId"):
            r[name]=reader.integer()
        r["isDoor"]=reader.boolean()
        r["OnceAngle"]=reader.integer()
        r["canFix"]=reader.boolean()
        n=reader.integer()
        if n<0 or n>100:raise ValueError("Invalid fix-material list length")
        r["fixMaterialInfos"]=[
            {"itemId":reader.integer(),"needNum":reader.integer()}
            for _ in range(n)]
        r["canRename"]=reader.boolean()
        r["canAutoUpgrade"]=reader.boolean()
        r["byte_span"]=[start,reader.off]
        if r["id"]<=0 or r["lv"]<0 or r["lv"]>100:
            raise ValueError("Bad BuildPart record at "+str(start))
        rows.append(r)
        if len(rows)>20000:raise ValueError("Unbounded BuildPart records")
    if len(rows)<10 or len({x["id"] for x in rows})!=len(rows):
        raise ValueError("No valid unique original cfg.BuildPart records")
    return rows

def verify_icons(rows, sprites):
    # A source icon name can appear in several bundles. Do NOT assign
    # arbitrarily; report candidate FileID/PathID and missing/ambiguous.
    lookup=collections.defaultdict(list)
    for bundle in sprites:
        for icon in bundle["icons"]:
            if not icon.get("file"):continue
            lookup[icon["name"]].append(
                {"bundle":bundle["bundle"],"path_id":icon["id"],
                 "file":icon["file"]})
    for row in rows:
        refs=lookup.get(row["icon"],[])
        row["verified_icon_candidates"]=refs
        row["icon_resolution"]=("unique" if len(refs)==1 else
                                "missing" if not refs else "ambiguous")
    return rows

def report_from_bytes(payload, sprites=None):
    rows=decode(payload)
    if sprites is not None:verify_icons(rows,sprites)
    basic=[r for r in rows if r["basic"] and r["lv"]==1]
    groups={}
    for t,cat in CATEGORIES.items():
        relevant=[r for r in basic if r["type"]==t]
        groups[cat]={"type_id":t,"count":len(relevant),
                     "items":relevant}
    return {
        "schema":"edgeai.unity-buildpart.v1",
        "source":SOURCE_PATH,
        "bytes":len(payload),
        "sha256":hashlib.sha256(payload).hexdigest(),
        "record_count":len(rows),
        "basic_level1_count":len(basic),
        "groups":groups,
        "all_records":rows,
        "original_source_order_preserved":True,
        "pixel_fidelity_proven":False,
        "notes":[
            "Format matches Share.Octets and cfg.BuildPart constructor",
            "Category menu includes only basic && lv == 1 per BuildManager.GetBasicPartByType",
            "Icon candidate is valid only when exact BuildPart.icon name resolves",
            "Model Prefab and material IDs are source fields, not proof of successful port",
        ],
    }

def read_source(parts_dir):
    parts=sorted(parts_dir.glob("Last_Island_LITE_7.3.xapk.part*"))
    if len(parts)!=17:raise ValueError("Expected 17 original XAPK parts")
    with tempfile.TemporaryDirectory() as td:
        merged=Path(td)/"orig.xapk"
        with merged.open("wb") as out:
            for part in parts:
                with part.open("rb") as src:shutil.copyfileobj(src,out,8*1024*1024)
        with zipfile.ZipFile(merged) as outer:
            base=Path(td)/"base.apk"
            with outer.open(APK_NAME) as src,base.open("wb") as dest:
                shutil.copyfileobj(src,dest,8*1024*1024)
        with zipfile.ZipFile(base) as apk:
            return apk.read(SOURCE_PATH)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--binary",type=Path)
    group.add_argument("--xapk-parts",type=Path)
    p.add_argument("--icons",type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    payload=args.binary.read_bytes() if args.binary else read_source(args.xapk_parts)
    sprites=json.loads(args.icons.read_text()) if args.icons else None
    report=report_from_bytes(payload,sprites)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print("EDGEAI_UNITY_BUILDPART_DECODE_PASS",report["record_count"],
          "basic",report["basic_level1_count"],
          "categories",[(k,v["count"]) for k,v in report["groups"].items()],
          flush=True)
if __name__=="__main__":
    main()
