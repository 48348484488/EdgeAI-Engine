"""Bounded, conservative register expression flow over ARM32 CFG + typed effects.

Recover provenance of ADD/SUB values and CMP->BEQ/BNE predicates. This
is NOT a path-feasibility proof for symbolic expressions, alias analysis,
or a C++ generator. Unsupported effects invalidate information.
"""
from collections import deque

MASK = 0xffffffff
ENTRY_REGS = ('r0', 'r1', 'r2', 'r3')


def _constant(value):
    return {'kind': 'constant', 'value': value & MASK}


def _resolve(operand, env):
    if operand['kind'] == 'immediate':
        return _constant(operand['value'])
    return env.get(operand['name'])


def _depth(expr):
    if not expr:
        return 0
    if expr['kind'] == 'binary_expression':
        return 1 + max(_depth(expr['left']), _depth(expr['right']))
    if expr['kind'] == 'shift_expression':
        return 1 + max(_depth(expr['value']), _depth(expr['amount']))
    return 1


def _binary(op, left, right, limit):
    if left is None or right is None:
        return None
    if left['kind'] == right['kind'] == 'constant':
        a, b = left['value'], right['value']
        functions = {'add': lambda: a + b, 'sub': lambda: a - b,
                     'and': lambda: a & b, 'ands': lambda: a & b,
                     'orr': lambda: a | b, 'orrs': lambda: a | b,
                     'eor': lambda: a ^ b}
        if op in functions:
            return _constant(functions[op]())
    if 1 + max(_depth(left), _depth(right)) > limit:
        return None
    return {'kind': 'binary_expression', 'operation': op,
            'left': left, 'right': right, 'width_bits': 32}


def _shift(op, value, amount, limit):
    if value is None or amount is None:
        return None
    base = op.rstrip('s')
    if base not in ('lsl', 'lsr', 'asr'):
        return None
    if amount['kind'] == 'constant':
        n = amount['value']
        if n > 32 or (base == 'lsl' and n == 32):
            return None
        if value['kind'] == 'constant':
            number = value['value']
            if base == 'lsl':
                return _constant(number << n)
            if base == 'lsr':
                return _constant(number >> n)
            signed = number if number < 0x80000000 else number - 0x100000000
            return _constant(signed >> n)
    if 1 + max(_depth(value), _depth(amount)) > limit:
        return None
    return {'kind': 'shift_expression', 'operation': base, 'value': value,
            'amount': amount, 'width_bits': 32}


def _flag_zero_test(state, result, pc):
    if result is None:
        state.pop('$comparison', None)
    else:
        state['$comparison'] = {'operation': 'zero_test', 'left': result,
                                'right': _constant(0), 'source_pc': pc}


def _signed32(value):
    return value if value < 0x80000000 else value - 0x100000000


def _transfer(effect, incoming, depth_limit):
    state = dict(incoming)
    kind = effect['kind']
    if kind == 'assignment':
        dest = effect['destination']
        if effect.get('predicate'):
            state.pop(dest, None)
        elif effect['operation'] in ('mov', 'movs'):
            value = _resolve(effect['source'], state)
            if value is None:
                state.pop(dest, None)
            else:
                state[dest] = value
            if effect.get('sets_flags'):
                _flag_zero_test(state, value, effect['pc'])
        elif effect['operation'] == 'movw':
            state[dest] = _constant(effect['source']['value'] & 0xffff)
        elif effect['operation'] == 'movt':
            old = state.get(dest)
            if old and old['kind'] == 'constant':
                state[dest] = _constant((old['value'] & 0xffff) | ((effect['source']['value'] & 0xffff) << 16))
            else:
                state.pop(dest, None)
    elif kind == 'binary':
        dest = effect['destination']
        operation = effect['operation']
        value = _binary(operation[:-1] if operation.endswith('s') else operation, state.get(effect['lhs']),
                        _resolve(effect['rhs'], state), depth_limit)
        if value is None:
            state.pop(dest, None)
        else:
            state[dest] = value
        if effect['sets_flags']:
            _flag_zero_test(state, value, effect['pc'])
    elif kind == 'flag_test':
        a = state.get(effect['lhs'])
        b = _resolve(effect['rhs'], state)
        op = effect['operation']
        if op == 'cmp' and a is not None and b is not None:
            state['$comparison'] = {'operation': 'cmp', 'left': a, 'right': b,
                                    'source_pc': effect['pc']}
        elif op in ('cmn', 'tst') and a is not None and b is not None:
            result = _binary('add' if op == 'cmn' else 'and', a, b, depth_limit)
            _flag_zero_test(state, result, effect['pc'])
        else:
            state.pop('$comparison', None)
    elif kind == 'memory_read':
        # The origin PC is known; the runtime memory value is not. A repeated
        # load instruction may produce different values on different iterations.
        state[effect['value_register']] = {'kind': 'opaque_memory_read', 'source_pc': effect['pc']}
        if effect['address']['mode'] != 'offset':
            state.pop(effect['address']['base'], None)
    elif kind == 'memory_write':
        if effect['address']['mode'] != 'offset':
            state.pop(effect['address']['base'], None)
    elif kind == 'shift':
        value = _shift(effect['operation'], state.get(effect['source']),
                       _resolve(effect['amount'], state), depth_limit)
        if value is None:
            state.pop(effect['destination'], None)
        else:
            state[effect['destination']] = value
        if effect.get('sets_flags'):
            _flag_zero_test(state, value, effect['pc'])
    elif kind == 'unary':
        state.pop(effect['destination'], None)
    elif kind == 'direct_branch':
        if effect.get('call'):
            for reg in ('r0', 'r1', 'r2', 'r3', 'r12', 'lr', '$comparison'):
                state.pop(reg, None)
            for reg in list(state):
                if isinstance(state[reg], dict) and state[reg].get('kind') == 'opaque_memory_read':
                    state.pop(reg, None)
    elif kind in ('indirect_branch', 'return_candidate', 'noop'):
        pass
    else:
        # Incomplete decoding must never justify a register value or flag.
        state.clear()
    return state


def _join(old, incoming):
    return {key: val for key, val in old.items() if incoming.get(key) == val}


def _comparison_condition(effect, state):
    cond = effect.get('predicate')
    compare = state.get('$comparison')
    if cond not in ('eq', 'ne', 'hi', 'ls', 'cs', 'cc', 'ge', 'lt', 'gt', 'le') or compare is None or (cond not in ('eq','ne') and compare['operation'] != 'cmp'):
        return {'predicate': cond, 'source': None, 'status': 'unknown_flags'}
    return {'predicate': cond, 'source': compare,
            'status': 'symbolic_expression_only'}


def _taken_proven(effect, state):
    cond = effect.get('predicate')
    cmp = state.get('$comparison')
    if cond not in ('eq', 'ne', 'hi', 'ls', 'cs', 'cc', 'ge', 'lt', 'gt', 'le') or cmp is None:
        return None
    if cond not in ('eq','ne') and cmp['operation'] != 'cmp':
        return None
    a, b = cmp['left'], cmp['right']
    if a['kind'] == b['kind'] == 'constant':
        eq = a['value'] == b['value']
        if cond == 'eq':
            return eq
        if cond == 'ne':
            return not eq
        if cond == 'hi':
            return a['value'] > b['value']
        if cond == 'ls':
            return a['value'] <= b['value']
        if cond == 'cs':
            return a['value'] >= b['value']
        if cond == 'cc':
            return a['value'] < b['value']
        signed_a, signed_b = _signed32(a['value']), _signed32(b['value'])
        return {'ge':signed_a >= signed_b, 'lt':signed_a < signed_b,
                'gt':signed_a > signed_b, 'le':signed_a <= signed_b}[cond]
    return None


def analyze(cfg, outline, max_steps=150000, expression_depth=5):
    """Monotone must-provenance flow; joins keep only identical expressions."""
    pcs = {pc for pc in cfg['reachable_pcs']}
    effects = {item['pc']: item for item in outline['instruction_effects']}
    if cfg['entry'] != outline['entry'] or pcs != set(effects):
        raise ValueError('CFG and ARM instruction effects do not match')
    if not 1 <= expression_depth <= 24 or max_steps < len(pcs):
        raise ValueError('invalid analysis budget')
    successors = {pc: [] for pc in pcs}
    for edge in cfg['cfg_edges']:
        if edge['from'] not in pcs or edge['to'] not in pcs:
            raise ValueError('edge outside instruction graph')
        successors[edge['from']].append((edge['to'], edge['type']))
    inputs = {reg: {'kind': 'entry_register', 'register': reg} for reg in ENTRY_REGS}
    states = {cfg['entry']: inputs}
    queue = deque([cfg['entry']])
    steps = 0
    while queue:
        pc = queue.popleft()
        steps += 1
        if steps > max_steps:
            raise ValueError('symbolic register flow did not converge inside budget')
        eff = effects[pc]
        before = states[pc]
        after = _transfer(eff, before, expression_depth)
        definite = _taken_proven(eff, before) if eff['kind'] == 'direct_branch' else None
        for dst, edge_kind in successors[pc]:
            if definite is not None and eff.get('predicate') in ('eq','ne','hi','ls','cs','cc','ge','lt','gt','le'):
                if edge_kind == 'taken' and not definite:
                    continue
                if edge_kind == 'fallthrough' and definite:
                    continue
            incoming = dict(after)
            if dst in states:
                incoming = _join(states[dst], incoming)
            if states.get(dst) != incoming:
                states[dst] = incoming
                queue.append(dst)
    conditions = []
    for pc in sorted(states, key=lambda val: int(val, 16)):
        eff = effects[pc]
        if eff['kind'] == 'direct_branch' and eff.get('predicate'):
            condition = _comparison_condition(eff, states[pc])
            condition['branch_pc'] = pc
            condition['outgoing_edges'] = [
                {'to': dest, 'type': kind} for dest, kind in successors[pc]]
            definite = _taken_proven(eff, states[pc])
            condition['edge_proven'] = ('taken' if definite else 'fallthrough') if definite is not None else None
            conditions.append(condition)
    result = dict(outline)
    result['register_flow'] = {
        'analyzed_instructions': len(states),
        'in_states': {pc: states[pc] for pc in sorted(states, key=lambda x: int(x, 16))},
        'branch_conditions': conditions,
        'unknown_instruction_pcs': sorted(
            (pc for pc in states if effects[pc]['kind'] == 'unsupported'),
            key=lambda x: int(x, 16)),
        'scope': 'Bounded ARM32 expression provenance. Branch equality of symbolic inputs is not proved; no memory alias proof or C++ equivalence.'
    }
    return result
