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

def _candidate_record(data, offset):
    """Validate next source record with original icon bundle and model paths."""
    try:
        r=Octets(data)
        r.off=offset
        ident=r.integer()
        typ=r.integer()
        function_type=r.integer()
        if not (100 <= ident <= 1_000_000 and
                1 <= typ <= 100 and 0 <= function_type <= 100_000):
            return False
        name=r.string()
        lv,revision,lv1,next_id=(r.integer() for _ in range(4))
        icon=r.string()
        if not (name and len(name)<=70 and 1<=lv<=1000 and
                0<=revision<=1000 and lv1>0 and
                icon.startswith("buildpart")):
            return False
        if r.pop("B") not in (0,1):return False
        model=r.string()
        return not model or model.startswith(("part/","model/","sceneprefab/"))
    except (UnicodeError,ValueError,IndexError,struct.error):
        return False

def decode(payload):
    """Decode only original fields whose offsets are verified against 7.3.

    The older decompiled BuildPart.cs differs from the XAPK by an additional
    integer after lv, a flag after basic and an omitted otherPlayerbtns
    string. The trailing record extension is version-dependent. Preserve its
    hash and scan for the next strongly validated BuildPart header rather
    than guessing extension fields. Fail closed when no boundary is found.
    """
    reader=Octets(payload)
    rows=[]
    while reader.off<len(reader.data):
        start=reader.off
        r={}
        for name in ("id","type","functionType"):
            r[name]=reader.integer()
        r["name"]=reader.string()
        for name in ("lv","unknown_version_level","lv1Id","nextId"):
            r[name]=reader.integer()
        r["icon"]=reader.string()
        r["canUpgrade"]=reader.boolean()
        r["model"]=reader.string()
        r["basic"]=reader.boolean()
        r["unknown_post_basic_flag"]=reader.boolean()
        for name in ("needSupportValue","destoryEffectId",
                     "buildEffectId","upLvEffectId"):
            r[name]=reader.integer()
        r["needCheck"]=reader.boolean()
        r["btns"]=[int(x) for x in reader.string().split("|") if x.lstrip("-").isdigit()]
        r["otherPlayerbtns"]=None  # Not present in 7.3 binary prefix.
        r["materialInfo"]={k:reader.integer() for k in
                           ("itemId","needNum","hp","returnNum")}
        for name in ("buildSoundId","destorySoundId","upSoundId"):
            r[name]=reader.integer()
        suffix_start=reader.off
        # Verified in source level-1 base parts: a 32-bit isDoor flag followed
        # by 32-bit OnceAngle. Do not claim angles for unverified structures.
        r["OnceAngle"]=None
        if r["type"] in CATEGORIES and suffix_start+8 <= len(payload):
            possible=struct.unpack_from("<i",payload,suffix_start+4)[0]
            if 0<=possible<=360:r["OnceAngle"]=possible
        remaining=len(payload)-suffix_start
        end=None
        for position in range(suffix_start,min(suffix_start+1500,len(payload)-10)):
            if _candidate_record(payload,position):
                end=position
                break
        if end is None:
            if remaining>1500:
                raise ValueError("Cannot establish source BuildPart record boundary "
                                 +str(r["id"])+" at "+str(suffix_start))
            end=len(payload)
        suffix=payload[suffix_start:end]
        r["extension_bytes"]=len(suffix)
        r["extension_sha256"]=hashlib.sha256(suffix).hexdigest()
        r["byte_span"]=[start,end]
        reader.off=end
        if r["id"]<=0 or r["lv"]<1 or r["type"]<1:
            raise ValueError("Bad BuildPart record at "+str(start))
        rows.append(r)
        if len(rows)>20000:raise ValueError("Unbounded BuildPart records")
    if len(rows)<10 or len({x["id"] for x in rows})!=len(rows):
        raise ValueError("No valid unique original cfg.BuildPart records")
    return rows

def verify_icons(rows, sprites):
    """Resolve exact 'buildpart/basename' -> assets/icon/buildpart.ab Sprite."""
    lookup=collections.defaultdict(list)
    for bundle in sprites:
        for icon in bundle["icons"]:
            if not icon.get("file"):continue
            lookup[(bundle["bundle"],icon["name"])].append(
                {"bundle":bundle["bundle"],"path_id":icon["id"],
                 "file":icon["file"]})
    for row in rows:
        icon=row["icon"].split("/")
        refs=[]
        if len(icon)==2:
            refs=lookup.get(("assets/icon/"+icon[0]+".ab",icon[1]),[])
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
            "Reader accounts for verified 7.3 Octets fields and version-dependent record extension",
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
