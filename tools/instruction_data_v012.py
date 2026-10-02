"""v0.12 synthetic curriculum: richer in-domain prompts while preserving v0.7 sealed tests."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import load_dataset,validate_dataset,sha,dumps

AUG={
'copy':(('Echo exactly: {s}','Ecoe exatamente: {s}'),('Output without changes: {s}','Responda sem alterar: {s}')),
'uppercase':(('Write in uppercase: {s}','Escreva em maiusculas: {s}'),('Capitalize every letter: {s}','Coloque todas as letras em maiusculas: {s}')),
'addition':(('Compute {a} plus {b}.','Calcule {a} mais {b}.'),('Return only the sum: {a}+{b}','Retorne apenas a soma: {a}+{b}')),
'expression':(('Give x {op} {k} as an expression.','De a expressao x {op} {k}.'),('Output exactly the expression x {op} {k}.','Retorne exatamente a expressao x {op} {k}.')),
}
def values(row):
    g=row['group']
    if row['task'] in ('copy','uppercase'): return dict(s=g.split(':',1)[1])
    if row['task']=='addition':
        _,a,b=g.split(':');return dict(a=int(a),b=int(b))
    if row['task']=='expression':
        k=int(g.split(':')[1]);op=row['answer'][1];return dict(op=op,k=k)
    raise ValueError(row['task'])
def augment(base):
    out={k:list(v) for k,v in base.items()}
    extra=[]
    for row in base['train']:
        v=values(row)
        for variant,pair in enumerate(AUG[row['task']]):
            template=pair[0 if row['language']=='en' else 1]
            nr=dict(row);nr['prompt']=template.format(**v);nr['template']=f"{row['task']}_{row['language']}_aug{variant+1}"
            nr['id']=sha(dumps(nr).encode())[:20];extra.append(nr)
    out['train']=sorted(out['train']+extra,key=lambda r:sha(('v012-order:'+r['id']).encode()))
    validate_dataset(out);return out
def write(root):
    base,_=load_dataset(ROOT/'data/instructions_v07');data=augment(base);root=Path(root);root.mkdir(parents=True,exist_ok=True);files={}
    for split,rows in data.items():
        raw=('\n'.join(dumps(r) for r in rows)+'\n').encode();(root/(split+'.jsonl')).write_bytes(raw)
        files[split+'.jsonl']=dict(sha256=sha(raw),rows=len(rows),bytes=len(raw))
    manifest=dict(format='edge-sft-synthetic-1',synthetic=True,source='v0.7 frozen splits plus deterministic in-domain train-only template augmentation',
      license='CC0-1.0',parent_manifest_sha256=sha((ROOT/'data/instructions_v07/manifest.json').read_bytes()),
      sealed_test_policy='test_id/test_template/test_range/test_family copied byte-for-byte from v0.7; no test prompt, group, range, or held-out family added to train',
      generator_sha256=sha(Path(__file__).read_bytes()),files=files)
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');return manifest
if __name__=='__main__':
    import argparse;p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'data/instructions_v012_aug');a=p.parse_args();print(json.dumps(write(a.out),indent=2))
