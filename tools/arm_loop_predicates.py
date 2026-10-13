"""Recover bounded ARM32 loop branch predicates from CFG and typed effects.

Identifies counter-update syntax and a comparison feeding the back edge.
Neither termination nor induction invariants are proven. Never generates C++.
"""

COMPARISONS = {'eq': '==', 'ne': '!=', 'hi': '>u', 'ls': '<=u',
               'cs': '>=u', 'cc': '<u', 'ge': '>=s', 'lt': '<s',
               'gt': '>s', 'le': '<=s'}


def analyze(cfg, enriched):
    if cfg['entry'] != enriched['entry']:
        raise ValueError('incompatible CFG and IR entries')
    effects = {row['pc']: row for row in enriched['instruction_effects']}
    if len(effects) != len(enriched['instruction_effects']):
        raise ValueError('duplicate instruction addresses')
    reachable = set(cfg['reachable_pcs'])
    if set(effects) != reachable:
        raise ValueError('CFG and decoded instruction sets disagree')
    edges = {}
    incoming = {}
    for item in cfg['cfg_edges']:
        src, dst = item['from'], item['to']
        if src not in reachable or dst not in reachable:
            raise ValueError('edge outside CFG')
        edges.setdefault(src, []).append((dst, item['type']))
        incoming.setdefault(dst, set()).add(src)
    results = []
    for loop in enriched.get('loops', []):
        header = loop['header']
        members = set(loop['body_pcs'])
        if header not in members or not members <= reachable:
            raise ValueError('invalid loop membership')
        exits = [{'from':src, 'to':dst, 'type':kind}
                 for src in sorted(members, key=lambda x:int(x,16))
                 for dst,kind in edges.get(src, []) if dst not in members]
        memory = [{'pc':pc, 'kind':effects[pc]['kind'],
                   'address':effects[pc]['address']}
                  for pc in sorted(members, key=lambda x:int(x,16))
                  if effects[pc]['kind'] in ('memory_read','memory_write')]
        parsed = []
        for latch in loop['latches']:
            branch = effects[latch]
            if branch['kind'] != 'direct_branch' or branch.get('call'):
                parsed.append({'latch':latch,'status':'unsupported_latch'})
                continue
            predicate = branch.get('predicate')
            if predicate not in COMPARISONS or branch['target'] != header:
                parsed.append({'latch':latch,'status':'unsupported_backedge_predicate'})
                continue
            if (header,'taken') not in edges.get(latch, []):
                parsed.append({'latch':latch,'status':'unverified_taken_backedge'})
                continue
            previous = [src for src in incoming.get(latch,set()) if src in members]
            if len(previous) != 1:
                parsed.append({'latch':latch,'status':'ambiguous_flag_producer'})
                continue
            flagpc = previous[0]
            flags = effects[flagpc]
            counter, bound, mode = None, None, None
            if flags['kind']=='flag_test' and flags['operation']=='cmp':
                rhs = flags['rhs']
                if rhs['kind']=='immediate':
                    counter,bound,mode=flags['lhs'],rhs['value'],'cmp_after_update'
            elif (flags['kind']=='binary' and flags.get('sets_flags')
                  and flags['operation'] in ('adds','subs')
                  and predicate in ('eq','ne')):
                counter,bound,mode=flags['destination'],0,'update_sets_zero'
            if counter is None:
                parsed.append({'latch':latch,'status':'flag_source_not_supported',
                               'flag_source_pc':flagpc})
                continue
            updates = [(pc,eff) for pc,eff in effects.items() if pc in members
                       and eff['kind']=='binary' and eff['operation'] in ('add','adds','sub','subs')
                       and eff['destination']==counter and eff['lhs']==counter
                       and eff['rhs']['kind']=='immediate']
            if len(updates)!=1:
                parsed.append({'latch':latch,'status':'nonunique_counter_update',
                               'counter':counter,'update_count':len(updates)})
                continue
            update_pc,update=updates[0]
            if mode=='update_sets_zero' and update_pc!=flagpc:
                parsed.append({'latch':latch,'status':'flag_update_disagrees_with_counter'})
                continue
            other_defs = [pc for pc in members if pc!=update_pc and
                          effects[pc].get('destination')==counter]
            if other_defs:
                parsed.append({'latch':latch,'status':'counter_has_other_definitions',
                               'definition_pcs':sorted(other_defs)})
                continue
            delta = update['rhs']['value']*(1 if update['operation'] in ('add','adds') else -1)
            parsed.append({'latch':latch,'status':'counter_candidate',
                           'counter_register':counter,'update_pc':update_pc,
                           'delta':delta,'comparison_pc':flagpc,'bound':bound,
                           'compare_mode':mode,'backedge_predicate':predicate,
                           'backedge_expression':f'{counter}_next {COMPARISONS[predicate]} {bound}',
                           'flags_provenance':'cmp_immediate' if mode=='cmp_after_update' else 'Z_only',
                           'iteration_count_proven':False})
        results.append({'loop_header':header,'latches':parsed,'exit_edges':exits,
                        'memory_accesses':memory,
                        'early_exit_edges':[e for e in exits if e['from'] not in loop['latches']],
                        'confidence':'syntactic_candidate_not_iteration_or_termination_proof'})
    return {'loops':results,'scope':'ARM32 CFG backedge and register counter syntax; no loop equivalence proof'}
