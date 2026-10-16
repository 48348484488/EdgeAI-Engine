#!/usr/bin/env python3
"""Combine independent blind binary-only game evidence without inflating claims."""
import argparse
import hashlib
import json
from pathlib import Path


def summarize(build, edgeai, ghidra, binary_hash):
    if build.get('binary_sha256') != binary_hash:
        raise ValueError('compiled binary digest mismatch')
    if edgeai.get('file_sha256') != binary_hash:
        raise ValueError('EdgeAI report does not match the exact ELF')
    if build.get('source_used_in_analysis') is not False:
        raise ValueError('build provenance does not guarantee blind split')
    if edgeai.get('target_executed') is not False:
        raise ValueError('static audit unexpectedly executed target')
    if ghidra.get('target_source_read') is not False:
        raise ValueError('Ghidra step used source')
    es = edgeai.get('summary', {})
    selected = es.get('functions_selected')
    completed = es.get('functions_completed')
    if not (isinstance(selected, int) and isinstance(completed, int)
            and 0 <= completed <= selected <= 64):
        raise ValueError('invalid audit counts')
    gfuncs = ghidra.get('functions', [])
    if not isinstance(gfuncs, list) or ghidra.get('functions_detected') != len(gfuncs):
        raise ValueError('incorrect Ghidra manifest')
    exported = sum(item.get('status') == 'GHIDRA_PSEUDOCODE' for item in gfuncs)
    if exported != ghidra.get('pseudocode_functions'):
        raise ValueError('Ghidra pseudocode count inconsistent')
    symbol_count = build['eligible_named_functions']
    if not isinstance(symbol_count, int) or symbol_count < 0:
        raise ValueError('invalid symbol count')
    return {
        'status': 'BLIND_EXTERNAL_GAME_EVIDENCE',
        'game_repo': build['upstream_repository'],
        'game_commit': build['upstream_commit'],
        'license': build['license'],
        'binary_sha256': binary_hash,
        'architecture': 'AArch64',
        'source_used_in_analysis': False,
        'source_available_in_analysis_job': False,
        'functions_eligible_by_elf_symbols': symbol_count,
        'functions_selected_edgeai': selected,
        'edgeai_functions_static_audited': completed,
        'edgeai_native_cpp_functions_recovered': 0,
        'ghidra_backend': ghidra['backend'],
        'ghidra_detected_functions_including_external_runtime_stubs': len(gfuncs),
        'ghidra_pseudocode_functions_including_external_runtime_stubs': exported,
        'binary_recompiled_from_pseudocode': False,
        'behavioral_equivalence_proven': False,
        'whole_game_autonomously_decompiled_by_edgeai': False,
        'requirements_20_to_50_named_functions_met': 20 <= symbol_count <= 50,
        'interpretation': (
            'EdgeAI performs static CFG and value-provenance auditing; Ghidra is an '
            'independent external pseudocode baseline. Counts are not percentage '
            'of functionally recovered game source.'
        ),
        'edgeai_unsupported': es['functions_unsupported_or_skipped'],
        'edgeai_table_patterns': es['table_patterns_in_completed_functions'],
        'limitations': [
            'Debug symbols and original source were not passed to the analysis job.',
            'Named function symbols remain in the EdgeAI audit ELF; stripped ELF is given to Ghidra.',
            'Ghidra pseudocode is not EdgeAI native reconstruction and might not compile.',
            'Ghidra may count PLT and runtime helper stubs, not just game functions.',
            'No differential run between original and reconstructed game was performed.',
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary', required=True, type=Path)
    p.add_argument('--build', required=True, type=Path)
    p.add_argument('--edgeai', required=True, type=Path)
    p.add_argument('--ghidra', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args(argv)
    digest = hashlib.sha256(a.binary.read_bytes()).hexdigest()
    inputs = [json.loads(f.read_text()) for f in (a.build, a.edgeai, a.ghidra)]
    report = summarize(*inputs, digest)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


if __name__ == '__main__':
    main()
