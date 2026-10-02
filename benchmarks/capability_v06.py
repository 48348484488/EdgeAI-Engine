#!/usr/bin/env python3
"""Explicit held-out utility checks. No arbitrary code execution, no shell/eval.

These 28 tiny authored tasks are diagnostics, not a standardized benchmark or
proof of broad intelligence. Neural answers and deterministic tools are separate.
"""
import argparse,ast,json,operator,random,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from external_data import load_snapshot,sha
OPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.FloorDiv:operator.floordiv,ast.Mod:operator.mod}

def restricted_expression(source,variables):
    if not isinstance(source,str) or len(source)>1024:raise ValueError('expression limit')
    tree=ast.parse(source,mode='eval')
    if sum(1 for _ in ast.walk(tree))>64:raise ValueError('AST too large')
    def run(node,depth=0):
        if depth>20:raise ValueError('depth limit')
        if isinstance(node,ast.Expression):value=run(node.body,depth+1)
        elif isinstance(node,ast.Constant) and type(node.value) is int:value=node.value
        elif isinstance(node,ast.Name) and node.id in variables:value=variables[node.id]
        elif isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            v=run(node.operand,depth+1);value=v if isinstance(node.op,ast.UAdd) else -v
        elif isinstance(node,ast.BinOp) and type(node.op) in OPS:value=OPS[type(node.op)](run(node.left,depth+1),run(node.right,depth+1))
        else:raise ValueError('operation not allowed')
        if type(value) is not int or abs(value)>10**12:raise ValueError('integer bound')
        return value
    return run(tree)

def tasks():
    rng=random.Random(606031);out=[]
    for i in range(12):
        a,b,c=[rng.randint(13,87) for _ in range(3)];expr=f'({a}+{b})*{c}' if i%2 else f'{a}*{b}-{c}';expected=(a+b)*c if i%2 else a*b-c
        out.append(dict(id=f'arith-{i}',category='arithmetic',prompt='Return only the integer result of '+expr+': ',expression=expr,expected=str(expected)))
    for i,s in enumerate(['azul-47','caixa_83','CPU-sem-GPU','papel-915','delta_604','memoria-28','janela_731','eco-502']):
        out.append(dict(id=f'copy-{i}',category='exact_instruction',prompt='Repeat exactly this text and nothing else: '+s+'\nAnswer: ',expected=s))
    for name,expression in [('add_values','a+b'),('subtract_values','a-b'),('multiply_values','a*b'),('square_first','a*a'),('twice_first_plus_second','2*a+b'),('difference_of_squares','a*a-b*b'),('sum_plus_one','a+b+1'),('remainder','a%b')]:
        prompt=f'# Complete the function to compute {expression}.\ndef {name}(a, b):\n    return '
        out.append(dict(id='code-'+name,category='restricted_code',prompt=prompt,reference_expression=expression,cases=[dict(a=a,b=b,expected=restricted_expression(expression,dict(a=a,b=b))) for a,b in [(3,2),(7,4),(-3,5),(0,6),(13,7)]]))
    return out

def score_task(task,raw):
    try:text=raw.decode('utf-8',errors='strict')
    except UnicodeError:return False
    if task['category']=='restricted_code':
        # The task asks for a return expression; only its first line is examined.
        expression=text.split('\n',1)[0].strip()
        try:return all(restricted_expression(expression,{'a':v['a'],'b':v['b']})==v['expected'] for v in task['cases'])
        except (ValueError,SyntaxError,TypeError,ZeroDivisionError,RecursionError,OverflowError):return False
    return text.strip()==task['expected']

def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,default=ROOT/'build');p.add_argument('--report',type=Path,default=ROOT/'results/v06/training.json');p.add_argument('--out',type=Path,default=ROOT/'results/v06/capability.json');a=p.parse_args()
    build=a.build.resolve();tr=json.loads(a.report.read_text());suite=tasks();snapshot=ROOT/'data/cpython_snapshot';m=load_snapshot(snapshot);train=[(snapshot/r['path']).read_bytes() for r in m['documents'] if r['split']=='train']
    leaked=[t['id'] for t in suite if any(t['prompt'].encode() in raw for raw in train)]
    if leaked:raise AssertionError('exact benchmark prompt in training sources: '+str(leaked))
    rows=[];tool_rows=[]
    with tempfile.TemporaryDirectory() as td:
        d=Path(td)
        for row in tr['runs']:
            results=[]
            for task in suite:
                (d/'prompt').write_bytes(task['prompt'].encode())
                subprocess.run([str(build/'edgeai_generate'),str(ROOT/row['model_path']),str(d/'prompt'),str(d/'output'),'48'],check=True,capture_output=True)
                raw=(d/'output').read_bytes();results.append(dict(task=task['id'],category=task['category'],passed=score_task(task,raw),output_hex=raw.hex(),output_utf8=raw.decode('utf-8','replace')))
            by={c:dict(passed=sum(r['passed'] for r in results if r['category']==c),total=sum(r['category']==c for r in results)) for c in ('arithmetic','restricted_code','exact_instruction')}
            rows.append(dict(kind=row['kind'],seed=row['seed'],categories=by,results=results))
        for task in suite:
            if task['category']!='arithmetic':continue
            process=subprocess.run([str(build/'edgeai_chat'),'--prompt',task['expression'],'--memory',str(d/'mem.txt')],check=True,capture_output=True,text=True)
            response=process.stdout.splitlines()[0].strip();tool_rows.append(dict(task=task['id'],response=response,passed=response==task['expected'],neural_used=False))
    report=dict(tasks=suite,task_count=len(suite),prompt_sha256=sha(json.dumps(suite,sort_keys=True).encode()),exact_prompts_found_in_train=leaked,
      neural=rows,deterministic_calculator=tool_rows,note='28 small tasks authored for this diagnostic; not an external standardized suite. No instruction fine-tuning. Greedy 48 tokens. Exact text match for arithmetic/copy; first-line return expression tested on 5 inputs. Restricted AST interpreter, no exec/eval/compilation of generated code. Tool results are NOT neural capability.')
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'models':len(rows),'tasks_per_model':len(suite),'calculator_passed':sum(r['passed'] for r in tool_rows),'neural':[{'kind':r['kind'],'seed':r['seed'],'categories':r['categories']} for r in rows]}))
if __name__=='__main__':main()
