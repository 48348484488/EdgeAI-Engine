"""Synthetic v0.13 curriculum: broader training support without contaminating sealed v0.12 tests."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from instruction_data import build_dataset,validate_dataset,dumps,sha

def build_v013():
    data=build_dataset()
    # Training-only curriculum expansion. Bounds deliberately stop before the
    # sealed v0.12 extrapolation ranges: addition train support <=29, expression <=39,
    # strings <=5 chars. Existing v0.12 test rows are never copied into train/valid.
    existing={(r['prompt'],r['answer']) for rows in data.values() for r in rows}
    def add(task,group,prompt,answer,language,template):
        key=(prompt,answer)
        if key in existing:return
        row=dict(task=task,group=group,prompt=prompt,answer=answer,language=language,template=template)
        row['id']=sha(dumps(row).encode())[:20];data['train'].append(row);existing.add(key)
    for a in range(20,30):
        for b in range(0,30):
            g=f'v013pair:{min(a,b)}:{max(a,b)}'
            add('addition',g,f'Add: {a} + {b}',str(a+b),'en','addition_en_v013')
            add('addition',g,f'Some: {a} + {b}',str(a+b),'pt','addition_pt_v013')
    for k in range(30,40):
        for op in ('+','-','*'):
            g=f'v013coef:{k}:{op}'
            add('expression',g,f'Expression for x {op} {k}:',f'x{op}{k}','en','expression_en_v013')
            add('expression',g,f'Expressao para x {op} {k}:',f'x{op}{k}','pt','expression_pt_v013')
    # Reverse is intentionally NOT added: test_family remains a truly unseen task.
    data['train']=sorted(data['train'],key=lambda r:r['id'])
    return data

def main():
    out=ROOT/'data/instructions_v013';out.mkdir(parents=True,exist_ok=True);data=build_v013()
    files={}
    for split,rows in data.items():
        raw=('\n'.join(dumps(r) for r in rows)+'\n').encode();(out/(split+'.jsonl')).write_bytes(raw)
        files[split+'.jsonl']=dict(sha256=sha(raw),rows=len(rows),bytes=len(raw))
    manifest=dict(format='edge-sft-synthetic-1',synthetic=True,source='deterministic local rules; v0.12 sealed tests retained',
      license='CC0-1.0',files=files,limitations=['diagnostic curriculum, not a standardized benchmark',
      'v0.12 test_range and test_family remain sealed; no test row is used for checkpoint selection',
      'reverse remains a fully held-out family'])
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))
if __name__=='__main__':main()
