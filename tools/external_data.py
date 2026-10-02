"""Freeze and validate independently authored installed CPython source files.

No network, no execution/import of corpus modules. Module families are split in
advance. Exact original bytes and licenses travel with the snapshot. Local OS
patches may exist: hashes identify this data, not an asserted upstream commit.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import sysconfig
import time

ROOT=Path(__file__).resolve().parents[1]
FAMILIES={
 'train':['abc.py','collections/__init__.py','contextlib.py','copy.py','enum.py','functools.py','heapq.py','pprint.py','random.py','string.py','textwrap.py','weakref.py'],
 'valid':['bisect.py','fractions.py','statistics.py'],
 'test':['graphlib.py','queue.py','sched.py'],
}
TOKENS=re.compile(rb'[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def shingles(raw):
    tokens=TOKENS.findall(raw)
    return {hashlib.blake2b(b'\x00'.join(tokens[i:i+5]),digest_size=8).digest() for i in range(max(0,len(tokens)-4))}
def normalized(raw):return b' '.join(TOKENS.findall(raw))
class DedupIndex:
    def __init__(self):self.sets=[];self.names=[];self.inverted=defaultdict(list);self.exact={}
    def duplicate(self,raw):
        sig=sha(normalized(raw))
        if sig in self.exact:return {'reference':self.exact[sig],'kind':'normalized_exact','containment':1.0}
        s=shingles(raw)
        if len(s)<8:return None
        candidates=Counter(i for sh in s for i in self.inverted.get(sh,()))
        for i,inter in candidates.most_common():
            union=len(s)+len(self.sets[i])-inter
            containment=inter/min(len(s),len(self.sets[i])) if self.sets[i] else 0
            if inter>=8 and (inter/union>=.8 or containment>=.9):
                return {'reference':self.names[i],'kind':'shingle_near_duplicate','containment':containment,'jaccard':inter/union}
        return None
    def add(self,raw,name):
        s=shingles(raw);i=len(self.sets);self.sets.append(s);self.names.append(name);self.exact[sha(normalized(raw))]=name
        for v in s:self.inverted[v].append(i)

def write_blocks(path,blocks):
    with Path(path).open('wb') as f:
        f.write(b'EDGRAW1\0');f.write(struct.pack('<I',len(blocks)))
        for raw in blocks:
            if not 1<=len(raw)<=4096:raise ValueError('bad raw block')
            f.write(struct.pack('<I',len(raw)));f.write(raw)

def read_blocks(path):
    data=Path(path).read_bytes()
    if len(data)<12 or data[:8]!=b'EDGRAW1\0':raise ValueError('invalid block format')
    count=struct.unpack_from('<I',data,8)[0]
    if not 1<=count<=1000000:raise ValueError('invalid block count')
    pos=12;out=[]
    for _ in range(count):
        if pos+4>len(data):raise ValueError('truncated block')
        n=struct.unpack_from('<I',data,pos)[0];pos+=4
        if not 1<=n<=4096 or pos+n>len(data):raise ValueError('invalid block length')
        out.append(data[pos:pos+n]);pos+=n
    if pos!=len(data):raise ValueError('trailing block data')
    return out

def freeze(stdlib,dest):
    stdlib=Path(stdlib).resolve();dest=Path(dest).resolve()
    if (dest/'manifest.json').exists():raise ValueError('snapshot already exists; do not silently replace it')
    dest.mkdir(parents=True,exist_ok=True);records=[];families=set();hashes=set();cpu=time.process_time();wall=time.perf_counter()
    for split,paths in FAMILIES.items():
        for name in paths:
            src=stdlib/name
            if not src.is_file():raise ValueError('missing independent source: '+str(src))
            raw=src.read_bytes();digest=sha(raw);family=name.split('/')[0].removesuffix('.py')
            if digest in hashes or family in families:raise ValueError('duplicate source/family across partitions')
            hashes.add(digest);families.add(family);target=Path('documents')/split/name
            (dest/target).parent.mkdir(parents=True,exist_ok=True);(dest/target).write_bytes(raw)
            records.append(dict(path=str(target),source_path=str(src),source_module=name,family=family,split=split,bytes=len(raw),sha256=digest))
    license_raw=(stdlib/'LICENSE.txt').read_bytes();(dest/'LICENSE-CPython.txt').write_bytes(license_raw)
    copyright_path=Path('/usr/share/doc/python3.13/copyright')
    licenses=[dict(path='LICENSE-CPython.txt',sha256=sha(license_raw),bytes=len(license_raw))]
    if copyright_path.is_file():
        raw=copyright_path.read_bytes();(dest/'COPYRIGHT-DISTRIBUTION.txt').write_bytes(raw)
        licenses.append(dict(path='COPYRIGHT-DISTRIBUTION.txt',sha256=sha(raw),bytes=len(raw)))
    index=DedupIndex()
    # Overlapping reference chunks improve shift tolerance; still not semantic dedup.
    for r in records:
        if r['split']=='train':
            raw=(dest/r['path']).read_bytes()
            for offset in range(0,len(raw)-31,128):index.add(raw[offset:offset+256],r['path']+':'+str(offset))
    block_manifest={}
    for split in ('valid','test'):
        kept=[];metadata=[];removed=[]
        for r in records:
            if r['split']!=split:continue
            raw=(dest/r['path']).read_bytes()
            for offset in range(0,len(raw),256):
                block=raw[offset:offset+256]
                if len(block)<32:continue
                name=r['path']+':'+str(offset);match=index.duplicate(block)
                if match:removed.append(dict(path=r['path'],offset=offset,**match));continue
                kept.append(block);metadata.append(dict(path=r['path'],offset=offset,bytes=len(block),sha256=sha(block)));index.add(block,name)
        if not kept:raise ValueError('no independent evaluation blocks')
        p=dest/(split+'.rawblocks');write_blocks(p,kept)
        block_manifest[split]=dict(path=p.name,sha256=sha(p.read_bytes()),bytes_scored=sum(map(len,kept)),kept=metadata,removed=removed)
    manifest=dict(format='edge-cpython-snapshot-1',source='installed CPython standard-library source, unmodified files',python_version=sys.version,
      upstream_reference='https://github.com/python/cpython',upstream_commit_verified=False,
      origin_caveat='Local distribution patches may exist. Reproduction uses these bundled hashes, not a presumed upstream tag.',
      license='PSF-2.0 and included notices; exact license files bundled',licenses=licenses,documents=records,
      totals={s:sum(r['bytes'] for r in records if r['split']==s) for s in FAMILIES},blocks=block_manifest,
      dedup=dict(tokens='ASCII identifiers/numbers/punctuation, whitespace-insensitive, case-sensitive',shingle=5,jaccard=.8,containment=.9,min_shared=8,reference_stride=128,block_bytes=256,semantic_dedup=False),
      preparation_cpu_seconds=time.process_time()-cpu,preparation_wall_seconds=time.perf_counter()-wall)
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (dest/'NOTICE.md').write_text('# CPython research snapshot\n\nCopyright (c) 2001-2024 Python Software Foundation. All Rights Reserved.\nOther notices are preserved in the source and included license files.\nFiles are copied unchanged from the installed runtime. Only file selection,\npartitioning and derived evaluation blocks were added by EdgeAI. This is not\nan official Python distribution. No Python or PSF endorsement is implied.\n')
    return manifest

def load_snapshot(root):
    root=Path(root).resolve();m=json.loads((root/'manifest.json').read_text())
    if m.get('format')!='edge-cpython-snapshot-1':raise ValueError('snapshot format')
    seen=set();family_split={}
    def verified(r):
        p=(root/r['path']).resolve()
        if not p.is_relative_to(root) or not p.is_file():raise ValueError('invalid snapshot path')
        raw=p.read_bytes()
        if sha(raw)!=r['sha256']:raise ValueError('snapshot hash mismatch: '+r['path'])
        return raw
    for r in m['documents']:
        if r['split'] not in FAMILIES or r['path'] in seen:raise ValueError('invalid split/duplicate document')
        if r['family'] in family_split and family_split[r['family']]!=r['split']:raise ValueError('family leakage')
        family_split[r['family']]=r['split'];seen.add(r['path']);raw=verified(r)
        if len(raw)!=r['bytes']:raise ValueError('source size mismatch')
    for r in m['licenses']:verified(r)
    for split in ('valid','test'):
        r=m['blocks'][split];verified(r);blocks=read_blocks(root/r['path'])
        if len(blocks)!=len(r['kept']) or sum(map(len,blocks))!=r['bytes_scored']:raise ValueError('block manifest mismatch')
        docs={d['path']:d for d in m['documents'] if d['split']==split}
        for block,meta in zip(blocks,r['kept']):
            if meta['path'] not in docs:raise ValueError('block source split mismatch')
            doc=(root/meta['path']).read_bytes()
            if sha(block)!=meta['sha256'] or block!=doc[meta['offset']:meta['offset']+meta['bytes']]:raise ValueError('block source mismatch')
    return m

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'data/cpython_snapshot');p.add_argument('--freeze-from',type=Path);a=p.parse_args()
    if a.freeze_from:freeze(a.freeze_from,a.root)
    m=load_snapshot(a.root);print(json.dumps({'documents':len(m['documents']),'raw_bytes':m['totals'],'evaluation':{s:{'kept':len(m['blocks'][s]['kept']),'removed':len(m['blocks'][s]['removed']),'bytes':m['blocks'][s]['bytes_scored']} for s in ('valid','test')}},indent=2))
if __name__=='__main__':main()
