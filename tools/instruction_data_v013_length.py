"""v0.13 length-bridge curriculum: add train-only 5-char copy/uppercase examples."""
from pathlib import Path
import itertools,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import dumps,sha
from instruction_data_v013 import build_v013

LENGTH5_STRINGS=512

def build_v013_length():
    data=build_v013()
    existing={(r['prompt'],r['answer']) for rows in data.values() for r in rows}
    candidates=[''.join(x) for x in itertools.product('abcdef',repeat=5)]
    candidates=sorted(candidates,key=lambda s:sha(('v013-length5:'+s).encode()))[:LENGTH5_STRINGS]
    def add(task,group,prompt,answer,language,template):
        key=(prompt,answer)
        if key in existing: raise ValueError('unexpected duplicate length-bridge row')
        row=dict(task=task,group=group,prompt=prompt,answer=answer,language=language,template=template)
        row['id']=sha(dumps(row).encode())[:20];data['train'].append(row);existing.add(key)
    for s in candidates:
        g='v013len5:'+s
        add('copy',g,'Copy exactly: '+s,s,'en','copy_en_v013_len5')
        add('copy',g,'Copie exatamente: '+s,s,'pt','copy_pt_v013_len5')
        add('uppercase',g,'Uppercase: '+s,s.upper(),'en','uppercase_en_v013_len5')
        add('uppercase',g,'Maiusculas: '+s,s.upper(),'pt','uppercase_pt_v013_len5')
    data['train']=sorted(data['train'],key=lambda r:r['id'])
    return data

def main():
    out=ROOT/'data/instructions_v013_length';out.mkdir(parents=True,exist_ok=True);data=build_v013_length();files={}
    for split,rows in data.items():
        raw=('\n'.join(dumps(r) for r in rows)+'\n').encode()
        (out/(split+'.jsonl')).write_bytes(raw)
        files[split+'.jsonl']=dict(sha256=sha(raw),rows=len(rows),bytes=len(raw))
    manifest=dict(format='edge-sft-synthetic-1',synthetic=True,
      source='v0.13 curriculum plus deterministic train-only 5-char string bridge',
      license='CC0-1.0',files=files,
      limitations=['diagnostic curriculum, not a standardized benchmark',
        'all v0.12 validation/test rows remain unchanged',
        'length-6 strings remain unseen in training'])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))
if __name__=='__main__': main()
