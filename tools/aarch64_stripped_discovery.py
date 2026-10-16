#!/usr/bin/env python3
"""Discover statically evidenced AArch64 function-entry *candidates* in stripped ELF.

Uses only executable section bytes and direct call encoding; no symbol table,
original source, network, execution or external Python dependencies. Return
candidate sites, never assert whole-program coverage or faithful C++ recovery.
"""
from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import struct

MAX_INPUT = 320 * 1024 * 1024
MAX_SECTIONS = 4096
MAX_TEXT = 32 * 1024 * 1024
MASK_IMM26 = (1 << 26) - 1


def _region(data, addr, length):
    if addr < 0 or length < 0 or addr > len(data) or length > len(data) - addr:
        raise ValueError('ELF section range is outside file')
    return data[addr:addr + length]


def load_text(path):
    path = Path(path)
    if not 64 <= path.stat().st_size <= MAX_INPUT:
        raise ValueError('ELF file size outside budget')
    data = path.read_bytes()
    if data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('expected little-endian ELF64')
    hdr = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    e_type, machine, version, entry, phoff, shoff, flags, ehsize, phentsize, phnum, shentsize, shnum, shstrndx = hdr
    if machine != 183 or version != 1 or e_type not in (2, 3) or not 1 <= shnum <= MAX_SECTIONS or shentsize < 64:
        raise ValueError('unsupported ELF class, architecture or sections')
    if shstrndx >= shnum:
        raise ValueError('bad section name table index')
    sections = [struct.unpack('<IIQQQQIIQQ', _region(data, shoff + i * shentsize, 64)) for i in range(shnum)]
    shstr = sections[shstrndx]
    strings = _region(data, shstr[4], shstr[5])
    matched = []
    for section in sections:
        name_off, stype, sflags, addr, off, size, link, info, align, entsize = section
        if name_off >= len(strings):
            raise ValueError('invalid ELF section name')
        name = strings[name_off:].split(b'\x00', 1)[0]
        if name == b'.text':
            if stype != 1 or not sflags & 4 or size == 0 or size > MAX_TEXT or addr % 4 or size % 4:
                raise ValueError('invalid AArch64 .text section')
            matched.append((addr, _region(data, off, size)))
    if len(matched) != 1:
        raise ValueError('expected exactly one executable .text section')
    return {'text_address': matched[0][0], 'text': matched[0][1],
            'elf_entry': entry, 'sha256': hashlib.sha256(data).hexdigest(),
            'file_size': len(data), 'elf_type': e_type}


def branch_imm26(pc, word):
    imm = (word & MASK_IMM26) << 2
    if imm & (1 << 27):
        imm -= 1 << 28
    return pc + imm


def _start_main_pointer_candidate(base, code, entry):
    """Recognize the conventional ELF AArch64 crt start's main address in x0.

    Require ADRP x0, ADD x0,x0,#imm, followed by an external BL to a PLT stub.
    This is a candidate based on crt call shape, not a recovered prototype.
    """
    end = base + len(code)
    if not base <= entry < end or entry % 4:
        return None
    for pc in range(entry, min(entry + 96, end - 8), 4):
        adr, = struct.unpack_from('<I', code, pc - base)
        add, = struct.unpack_from('<I', code, pc + 4 - base)
        if adr & 0x9F00001F != 0x90000000:
            continue
        if add & 0xFF8003FF != 0x91000000:
            continue
        imm = ((adr >> 29) & 3) | (((adr >> 5) & 0x7ffff) << 2)
        if imm & (1 << 20):
            imm -= (1 << 21)
        page = (pc & ~4095) + (imm << 12)
        shift = (add >> 22) & 1
        dest = page + (((add >> 10) & 0xfff) << (12 if shift else 0))
        if not base <= dest < end or dest % 4:
            continue
        for following in range(pc + 8, min(pc + 32, end), 4):
            w, = struct.unpack_from('<I', code, following - base)
            if w & 0xfc000000 == 0x94000000:
                if not base <= branch_imm26(following, w) < end:
                    return dest
    return None


def analyze(path):
    info = load_text(path)
    base, code = info['text_address'], info['text']
    end = base + len(code)
    evidence = defaultdict(set)
    incoming = defaultdict(list)
    branch_targets = []
    prologues = []
    for i in range(0, len(code), 4):
        pc = base + i
        word, = struct.unpack_from('<I', code, i)
        opcode = word & 0xFC000000
        if opcode in (0x94000000, 0x14000000):
            target = branch_imm26(pc, word)
            if base <= target < end and target % 4 == 0:
                if opcode == 0x94000000:
                    evidence[target].add('direct_bl_target')
                    incoming[target].append(hex(pc))
                else:
                    branch_targets.append(target)
        if (word & 0xFFC07FFF) == 0xA9807BFD:
            evidence[pc].add('frame_record_prologue')
            prologues.append(pc)
    if base <= info['elf_entry'] < end:
        evidence[info['elf_entry']].add('ELF_entry')
    main_ptr = _start_main_pointer_candidate(base, code, info['elf_entry'])
    if main_ptr is not None:
        off = main_ptr - base
        for step in range(4):
            if off + 4 > len(code):
                break
            w, = struct.unpack_from('<I', code, off)
            if w == 0xd503201f:
                off += 4
                continue
            if (w & 0xfc000000) == 0x14000000:
                target = branch_imm26(base + off, w)
                if base <= target < end and target % 4 == 0:
                    evidence[target].add('crt_main_pointer_thunk_target')
                    break
            if step == 0:
                evidence[main_ptr].add('crt_main_address_candidate')
            break
    # Direct B destinations are overwhelmingly basic-block edges, not entries;
    # do not promote them except with independent BL, prologue or CRT evidence.
    for target in branch_targets:
        if target in evidence:
            evidence[target].add('also_direct_b_target')
    candidates = []
    for addr in sorted(evidence):
        candidates.append({
            'address': hex(addr), 'evidence': sorted(evidence[addr]),
            'incoming_direct_bl_count': len(incoming.get(addr, ())),
            'incoming_direct_bl_sites': incoming.get(addr, ())[:20],
            'is_proven_function': False,
        })
    totals = Counter(label for row in candidates for label in row['evidence'])
    return {
        'status': 'STRIPPED_AARCH64_STATIC_ENTRY_CANDIDATES',
        'algorithm': 'ELF64 executable section + decoded BL immediate + frame record prologues',
        'input_sha256': info['sha256'],
        'arch': 'AArch64', 'source_read': False, 'symbols_used': False,
        'target_executed': False, 'original_source_decompiled': False,
        'elf_type': 'ET_EXEC' if info['elf_type'] == 2 else 'ET_DYN',
        'text_address': hex(base), 'text_size_bytes': len(code),
        'instruction_slots_scanned': len(code) // 4,
        'direct_bl_targets_within_text': totals['direct_bl_target'],
        'frame_record_prologues': len(prologues),
        'candidate_entry_count': len(candidates),
        'candidate_entries': candidates,
        'limitations': [
            'Direct BL destinations and frame prologues are candidate boundaries, not proof of functions.',
            'Tail calls with no BL and leaf functions without a frame record may be missed.',
            'Inner jump targets and indirect control flow are not exhaustively explored.',
            'No source code, variable types, runtime behavior or C++ was recovered.'
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = analyze(a.elf)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'candidate_entries'}, indent=2))


if __name__ == '__main__':
    main()
