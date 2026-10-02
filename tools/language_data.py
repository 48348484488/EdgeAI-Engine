"""Byte-level document data with explicit splits and no cross-document examples."""
import bisect
import hashlib
import json
import math
import random
import struct
import zipfile
from pathlib import Path
import torch

def sha256(data):return hashlib.sha256(data).hexdigest()
def bits_per_byte(nll,total):
    if total<=0 or not math.isfinite(nll) or nll<0:raise ValueError('invalid NLL/count')
    return nll/(total*math.log(2))
def make_blocks(documents,seq):
    if seq<1:raise ValueError('sequence length must be positive')
    blocks=[]
    for raw in documents:
        for start in range(0,len(raw)-1,seq):
            end=min(start+seq,len(raw)-1)
            blocks.append((list(raw[start:end]),list(raw[start+1:end+1])))
    return blocks

def remove_overlap(blocks,training_docs):
    kept=[];removed=0
    for x,y in blocks:
        raw=bytes(x)+bytes(y[-1:])
        if any(raw in doc for doc in training_docs):removed+=1
        else:kept.append((x,y))
    return kept,removed

def sample_batch(documents,batch_size,seq,generator):
    if min(batch_size,seq)<1:raise ValueError('positive batch/sequence required')
    docs=[d for d in documents if len(d)>seq]
    counts=[];total=0
    for doc in docs:total+=len(doc)-seq;counts.append(total)
    if not total:raise ValueError('no document long enough for training sequence')
    starts=torch.randint(total,(batch_size,),generator=generator).tolist();xs=[];ys=[]
    for offset in starts:
        index=bisect.bisect_right(counts,offset);start=offset-(counts[index-1] if index else 0)
        raw=docs[index][start:start+seq+1];xs.append(list(raw[:-1]));ys.append(list(raw[1:]))
    return torch.tensor(xs,dtype=torch.long),torch.tensor(ys,dtype=torch.long)

def write_blocks(blocks,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as f:
        f.write(b'EDGBLK1\0');f.write(struct.pack('<I',len(blocks)))
        for x,y in blocks:
            if not 1<=len(x)<=4096 or len(x)!=len(y) or x[1:]!=y[:-1]:raise ValueError('invalid shifted block')
            f.write(struct.pack('<I',len(x)));f.write(bytes(x)+bytes(y[-1:]))

def snapshot_archive(archive,out,seed=20260925):
    """Freeze the existing project corpus; never include newly written v0.5 code."""
    archive=Path(archive);out=Path(out)
    if (out/'manifest.json').exists():
        m=load_manifest(out)
        if m['archive_sha256']!=sha256(archive.read_bytes()):raise ValueError('frozen corpus archive changed')
        return m
    groups={'code':{},'text':{}};seen=set();duplicates=[]
    with zipfile.ZipFile(archive) as z:
        for name in sorted(z.namelist()):
            p=Path(name);parts=p.parts[1:]
            if not parts or '..' in parts:continue
            rel=Path(*parts);domain=None
            if rel.suffix in ('.cpp','.hpp') and parts[0] in ('src','include'):domain='code'
            elif str(rel) in ('README.md','docs/FORMAT.md','docs/FORMAT-v0.4.md','docs/DESIGN-v0.3.md','docs/DESIGN-v0.4.md','docs/PROTOCOL-v0.4.md','docs/IMPLEMENTATION-v0.3.md','docs/IMPLEMENTATION-v0.4.md'):domain='text'
            if domain is None:continue
            raw=z.read(name)
            if len(raw)<65:continue
            digest=sha256(raw)
            if digest in seen:duplicates.append(str(rel));continue
            seen.add(digest)
            # A C++ header and its implementation are kept in the same split.
            group=rel.stem if domain=='code' else str(rel)
            groups[domain].setdefault(group,[]).append((str(rel),raw))
    entries=[]
    for domain,families in groups.items():
        keys=sorted(families);random.Random(seed+(0 if domain=='code' else 1)).shuffle(keys)
        n=len(keys);nv=max(1,round(n*.15));nt=max(1,round(n*.15))
        if n<=nv+nt:raise ValueError('not enough document families')
        for i,key in enumerate(keys):
            split='valid' if i<nv else 'test' if i<nv+nt else 'train'
            for original,raw in families[key]:
                relative=Path('documents')/split/domain/original
                dest=out/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
                entries.append(dict(path=relative.as_posix(),source=original,domain=domain,split=split,group=key,bytes=len(raw),sha256=sha256(raw)))
    manifest=dict(schema=1,source='EdgeAI v0.4 own project source/documentation; predominantly generated during development, not independent human corpus',archive_sha256=sha256(archive.read_bytes()),split_seed=seed,documents=entries,removed_duplicate_files=duplicates)
    manifest['dataset_id']=sha256(json.dumps(manifest,sort_keys=True).encode())
    out.mkdir(parents=True,exist_ok=True);(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return load_manifest(out)

def load_manifest(root):
    root=Path(root);m=json.loads((root/'manifest.json').read_text());seen={};families={}
    expected=m.get('dataset_id');computed=sha256(json.dumps({k:v for k,v in m.items() if k!='dataset_id'},sort_keys=True).encode())
    if computed!=expected:raise ValueError('dataset manifest identity mismatch')
    for row in m['documents']:
        path=root/row['path']
        if not path.resolve().is_relative_to(root.resolve()):raise ValueError('dataset path escapes root')
        raw=path.read_bytes()
        if sha256(raw)!=row['sha256'] or len(raw)!=row['bytes']:raise ValueError('corpus checksum mismatch: '+row['path'])
        if row['sha256'] in seen:raise ValueError('duplicate corpus document')
        seen[row['sha256']]=row['split']
        key=(row['domain'],row['group']);old=families.setdefault(key,row['split'])
        if old!=row['split']:raise ValueError('related document family crosses splits')
    return m

def documents(root,manifest,split,domain=None):
    return [(Path(root)/r['path']).read_bytes() for r in manifest['documents'] if r['split']==split and (domain is None or r['domain']==domain)]

def evaluation_blocks(root,manifest,split,seq):
    if split not in ('valid','test'):raise ValueError('invalid evaluation split')
    reference=documents(root,manifest,'train')
    if split=='test':reference+=documents(root,manifest,'valid')
    result={};stats={}
    for domain in ('code','text'):
        blocks=make_blocks(documents(root,manifest,split,domain),seq)
        clean,removed=remove_overlap(blocks,reference)
        if not clean:raise ValueError('no nonduplicate evaluation blocks')
        result[domain]=clean;stats[domain]=dict(raw_blocks=len(blocks),removed_exact_overlap=removed,kept_blocks=len(clean),targets=sum(len(y) for x,y in clean))
    return result,stats
