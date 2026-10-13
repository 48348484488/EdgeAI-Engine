"""Attach conservative ARM32 instruction effects to structural IR.

Supported syntax is decoded; unknown instructions are retained verbatim.
This is not symbolic execution, a memory alias proof, or C++ decompilation.
"""
import re

REG = r'(?:r(?:1[0-5]|[0-9])|sp|lr|pc)'
IMM = r'#-?(?:0x[0-9a-fA-F]+|[0-9]+)'
VALUE = rf'(?:{REG}|{IMM})'
PAIR = re.compile(rf'^({REG}),\s*({VALUE})$')
TRIPLE = re.compile(rf'^({REG}),\s*({REG}),\s*({VALUE})$')
MEM = re.compile(rf'^({REG}),\s*\[({REG})(?:,\s*([^\]]+))?\](!)?(?:,\s*({IMM}))?$')
SHIFT = re.compile(rf'^({REG}),\s*lsl\s+#(\d+)$')
TARGET = re.compile(r'^0x([0-9a-fA-F]+)(?:\s|$)')
CONDITIONS = ('eq','ne','hi','ls','cs','cc','ge','lt','gt','le','mi','pl','vs','vc')
MEMORY = {'ldr','ldrb','ldrh','str','strb','strh'}
BINARY = {'add','adds','sub','subs','and','ands','orr','orrs','eor','eors'}


def _value(raw):
    return ({'kind':'immediate','value':int(raw[1:],0)} if raw.startswith('#')
            else {'kind':'register','name':raw})


def _unknown(pc,op,args,reason):
    return {'pc':pc,'mnemonic':op,'operands':args,'kind':'unsupported','reason':reason}


def decode(row):
    pc = hex(int(row['pc'],16)) if isinstance(row['pc'],str) else hex(row['pc'])
    op = row['mnemonic'].lower()
    args = row.get('operands','').strip()
    basic = {'pc':pc,'mnemonic':op,'operands':args}
    base,predicate=op,None
    for cond in CONDITIONS:
        if op.endswith(cond) and op[:-2] in {'mov','movw','movt'}:
            base,predicate=op[:-2],cond
            break
    if op == 'movs':
        base = 'movs'
    if base in {'mov','movs','movw','movt'}:
        m=PAIR.fullmatch(args)
        if m:
            if base in {'movw','movt'} and not m[2].startswith('#'):
                return _unknown(pc,op,args,'move-wide requires immediate')
            return {**basic,'kind':'assignment','operation':base,'destination':m[1],
                    'source':_value(m[2]),'predicate':predicate,
                    'sets_flags':base=='movs'}
    if op in {'cmp','cmn','tst'}:
        m=PAIR.fullmatch(args)
        if m:
            return {**basic,'kind':'flag_test','operation':op,
                    'lhs':m[1],'rhs':_value(m[2])}
    if op in BINARY:
        m=TRIPLE.fullmatch(args)
        if m:
            return {**basic,'kind':'binary','operation':op,
                    'destination':m[1],'lhs':m[2],'rhs':_value(m[3]),
                    'sets_flags':op.endswith('s')}
    if op=='clz':
        m=PAIR.fullmatch(args)
        if m and not m[2].startswith('#'):
            return {**basic,'kind':'unary','operation':op,
                    'destination':m[1],'source':m[2]}
    if op in {'lsl','lsr','asr','lsls','lsrs','asrs'}:
        m=TRIPLE.fullmatch(args)
        if m:
            return {**basic,'kind':'shift','operation':op,'destination':m[1],
                    'source':m[2],'amount':_value(m[3]),
                    'sets_flags':op.endswith('s')}
    if op in MEMORY:
        m=MEM.fullmatch(args)
        if m:
            reg,base_reg,offset,pre,post=m.groups()
            index={'kind':'none'}
            if offset:
                offset=offset.strip()
                shifted=SHIFT.fullmatch(offset)
                if shifted:
                    n=int(shifted[2])
                    if n>31:
                        return _unknown(pc,op,args,'invalid shift count')
                    index={'kind':'scaled_register','register':shifted[1],'shift':n}
                elif re.fullmatch(VALUE,offset):
                    index=_value(offset)
                else:
                    return _unknown(pc,op,args,'unrecognized addressing offset')
            if post and (pre or offset):
                return _unknown(pc,op,args,'ambiguous memory writeback')
            return {**basic,'kind':'memory_read' if op.startswith('ldr') else 'memory_write',
                    'value_register':reg,'width_bytes':1 if op.endswith('b') else 2 if op.endswith('h') else 4,
                    'address':{'base':base_reg,'index':index,
                               'mode':'post_index' if post else 'pre_index' if pre else 'offset',
                               'post_increment':int(post[1:],0) if post else None},
                    'alias_proven':False}
    if op=='b' or op=='bl' or (op.startswith('b') and op[1:] in CONDITIONS):
        m=TARGET.match(args)
        if m:
            return {**basic,'kind':'direct_branch','target':hex(int(m[1],16)),
                    'predicate':op[1:] if op not in ('b','bl') else None,'call':op=='bl'}
    if op=='bx' or (op.startswith('bx') and op[2:] in CONDITIONS):
        if re.fullmatch(REG,args):
            return {**basic,'kind':'indirect_branch','register':args,
                    'potential_return':args in ('lr','r14'),
                    'predicate':op[2:] or None}
    if op=='pop' and re.search(r'\b(?:pc|r15)\b',args):
        return {**basic,'kind':'return_candidate','register_source':'stack'}
    if op=='nop':
        return {**basic,'kind':'noop'}
    return _unknown(pc,op,args,'opcode or operands outside supported subset')


def attach(outline,instructions,reachable_pcs=None,max_instructions=20000):
    """One effect per reachable instruction, annotated with loop/if membership."""
    rows={}
    for row in instructions:
        pc=hex(int(row['pc'],16)) if isinstance(row['pc'],str) else hex(row['pc'])
        if pc in rows:
            raise ValueError('duplicate instruction address')
        rows[pc]=row
    if not rows or len(rows)>max_instructions:
        raise ValueError('invalid instruction budget')
    reachable=set(reachable_pcs) if reachable_pcs is not None else set(rows)
    if not reachable <= set(rows) or outline['entry'] not in reachable:
        raise ValueError('missing reachable ARM instruction')
    for loop in outline['loops']:
        if not set(loop['body_pcs']) <= reachable:
            raise ValueError('loop member outside decoded instruction set')
    for branch in outline['conditionals'] + outline['unstructured']:
        if branch['branch_pc'] not in reachable:
            raise ValueError('branch outside decoded instruction set')
    effects=[]
    for pc in sorted(reachable,key=lambda x:int(x,16)):
        item=decode(rows[pc])
        item['region_context']={
            'loops':[loop['header'] for loop in outline['loops'] if pc in loop['body_pcs']],
            'if_arms':[{'branch_pc':branch['branch_pc'],'arm':arm}
                       for branch in outline['conditionals'] if branch['kind']=='if_else'
                       for arm,key in (('then','then_pcs'),('else','else_pcs'))
                       if pc in branch[key]],
            'branches':[branch['kind'] for branch in outline['conditionals']
                        if branch['branch_pc']==pc]
        }
        effects.append(item)
    output=dict(outline)
    output['instruction_effects']=effects
    output['semantic_coverage']={
        'recognized':sum(x['kind']!='unsupported' for x in effects),
        'unsupported':sum(x['kind']=='unsupported' for x in effects),
        'status':'decoded_instruction_shapes_only_not_equivalence',
        'limitations':'No register values, alias proof, ABI recovery or C++ generation'
    }
    return output
