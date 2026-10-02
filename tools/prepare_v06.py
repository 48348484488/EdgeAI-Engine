#!/usr/bin/env python3
"""Reproduce tokenizers from frozen TRAIN only; refuse changed artifacts."""
import json,time
from pathlib import Path
from byte_bpe import ByteBPE
from external_data import ROOT,load_snapshot,sha
root=ROOT/'data/cpython_snapshot'
def main():
    m=load_snapshot(root);docs=[(root/r['path']).read_bytes() for r in m['documents'] if r['split']=='train'];cpu=time.process_time();wall=time.perf_counter();t=ByteBPE.train(docs,513)
    existing=ByteBPE.load(root/'tokenizers/bpe513.json');byte=ByteBPE.load(root/'tokenizers/byte257.json')
    if t.fingerprint()!=existing.fingerprint() or byte.merges:raise AssertionError('frozen tokenizer does not match train-only reproduction')
    report=dict(train_document_hashes=[r['sha256'] for r in m['documents'] if r['split']=='train'],snapshot_sha256=sha((root/'manifest.json').read_bytes()),cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,train_only=True,exact_reproduction=True,fingerprints={'bpe513':t.fingerprint(),'byte257':byte.fingerprint()})
    path=ROOT/'results/v06/tokenizer_reproduction.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
