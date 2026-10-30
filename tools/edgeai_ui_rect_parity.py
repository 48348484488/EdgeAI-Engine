#!/usr/bin/env python3
"""Compare source-backed UI rectangles and native render/touch geometry.

Deterministic static geometry audit. It does not prove screenshot, font,
animation, game-state, or touch-event runtime parity.
"""
import argparse
import json
import math
from pathlib import Path

SCHEMA = 'edgeai.ui-rect-parity.v1'


def rect(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f'{label} must contain [x,y,width,height]')
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) for v in value):
        raise ValueError(f'{label} must contain finite numbers')
    x, y, w, h = map(float, value)
    if w <= 0 or h <= 0:
        raise ValueError(f'{label} must have positive width and height')
    return x, y, w, h


def intersection(a, b):
    x = max(a[0], b[0]); y = max(a[1], b[1])
    w = max(0., min(a[0]+a[2], b[0]+b[2])-x)
    h = max(0., min(a[1]+a[3], b[1]+b[3])-y)
    return w*h


def area(a):
    return a[2]*a[3]


def analyze(data, max_edge_delta=0.5, max_dead_fraction=0.01):
    if data.get('schema') != SCHEMA:
        raise ValueError('unsupported geometry schema')
    if not isinstance(data.get('reference_provenance'), str) or not data['reference_provenance'].strip():
        raise ValueError('reference provenance is required')
    src = rect([0, 0, *data['reference_canvas']], 'reference_canvas')
    dst = rect([0, 0, *data['candidate_canvas']], 'candidate_canvas')
    sx, sy = dst[2]/src[2], dst[3]/src[3]
    controls = data.get('controls')
    if not isinstance(controls, list) or not controls:
        raise ValueError('nonempty controls list required')
    names = set(); results = []
    for item in controls:
        name = item.get('name') if isinstance(item, dict) else None
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError('missing or duplicate control name')
        names.add(name)
        reference = rect(item.get('reference'), name+'.reference')
        render = rect(item.get('render'), name+'.render')
        hit = rect(item.get('hit'), name+'.hit')
        expected = (reference[0]*sx, reference[1]*sy,
                    reference[2]*sx, reference[3]*sy)
        delta = [round(abs(a-b), 5) for a, b in zip(expected, render)]
        covered = intersection(render, hit)/area(render)
        dead_fraction = max(0., 1.-covered)
        issues = []
        if max(delta) > max_edge_delta:
            issues.append('source_render_geometry_mismatch')
        if dead_fraction > max_dead_fraction:
            issues.append('rendered_button_not_fully_touchable')
        results.append({'name': name, 'source_render_max_delta_px': max(delta),
                        'render_hit_dead_fraction': round(dead_fraction, 6),
                        'issues': issues})
    return {'schema': SCHEMA, 'reference_provenance': data['reference_provenance'],
            'analysis': 'static_rectangles_only', 'controls_checked': len(results),
            'issues': sum(len(x['issues']) for x in results), 'controls': results,
            'visual_or_behavioral_parity_proven': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args()
    report = analyze(json.loads(args.input.read_text(encoding='utf-8')))
    result = json.dumps(report, indent=2, ensure_ascii=False)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding='utf-8')
    print(result, end='')
    if args.strict and report['issues']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
