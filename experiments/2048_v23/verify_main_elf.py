#!/usr/bin/env python3
"""Source-blind ELF contract guard for the V23 host-side main-loop candidate.

Requires llvm-objdump and the original, independently pinned AArch64 ELF.
This checks disassembly provenance/shape, NOT runtime equivalence.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

EXPECTED_SHA = 'a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b'
START, END = 0x401758, 0x401988
# Binary opcode and semantic cues independently pinned from original disassembly.
REQUIRED = {
    0x401780: ('97ffffe1', 'bl', '0x401704'),
    0x401798: ('ad400660', 'ldp', 'q0, q1, [x19]'),
    0x4017a4: ('ad010400', 'stp', 'q0, q1, [x0, #0x20]'),
    0x4017f8: ('ad4006a0', 'ldp', 'q0, q1, [x21]'),
    0x401804: ('ad010660', 'stp', 'q0, q1, [x19, #0x20]'),
    0x401850: ('97fffc0c', 'bl', 'getchar@plt'),
    0x401874: ('540006a0', 'b.eq', '0x401948'),
    0x40187c: ('54fffa80', 'b.eq', '0x4017cc'),
    0x401884: ('54fffba0', 'b.eq', '0x4017f8'),
    0x4018a0: ('54000160', 'b.eq', '0x4018cc'),
    0x4018ac: ('54fffc80', 'b.eq', '0x40183c'),
    0x4018b4: ('54fffce1', 'b.ne', '0x401850'),
    0x4018e0: ('ad400680', 'ldp', 'q0, q1, [x20]'),
    0x4018ec: ('ad0106a0', 'stp', 'q0, q1, [x21, #0x20]'),
    0x401914: ('36000120', 'tbz', 'w0, #0x0, 0x401938'),
    0x401920: ('3607f980', 'tbz', 'w0, #0x0, 0x401850'),
    0x40194c: ('97fffe20', 'bl', '0x4011cc'),
    0x401980: ('d65f03c0', 'ret', ''),
}
INSTRUCTION = re.compile(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+([a-z][\w.]*)\s*(.*?)\s*$')


def verify(elf: Path, disassembler: str):
    sha = hashlib.sha256(elf.read_bytes()).hexdigest()
    if sha != EXPECTED_SHA:
        raise ValueError(f'ELF SHA-256 mismatch: {sha} != {EXPECTED_SHA}')
    completed = subprocess.run(
        [disassembler, '-d', f'--start-address=0x{START:x}',
         f'--stop-address=0x{END:x}', str(elf)],
        check=True, text=True, capture_output=True, timeout=20)
    instructions = {}
    for line in completed.stdout.splitlines():
        match = INSTRUCTION.match(line)
        if not match:
            continue
        addr, opcode, mnemonic, operands = match.groups()
        pc = int(addr, 16)
        if START <= pc < END:
            if pc in instructions:
                raise ValueError(f'duplicate instruction 0x{pc:x}')
            instructions[pc] = (opcode, mnemonic, operands.split(' //')[0].strip())
    if len(instructions) != 140 or set(instructions) != set(range(START, END, 4)):
        raise ValueError(f'incomplete/incorrect main disassembly: {len(instructions)} instructions')
    for pc, (opcode, mnemonic, operand_part) in REQUIRED.items():
        got = instructions[pc]
        if got[0] != opcode or got[1] != mnemonic or operand_part not in got[2]:
            raise ValueError(f'0x{pc:x}: expected {(opcode,mnemonic,operand_part)}, got {got}')
    simd = [(pc, ins) for pc, ins in instructions.items()
            if ins[1] in ('ldp', 'stp') and ins[2].startswith('q')]
    if len(simd) != 16:
        raise ValueError(f'expected 16 SIMD board-copy instructions, found {len(simd)}')
    return {
        'sha256': sha, 'start': hex(START), 'end_exclusive': hex(END),
        'instruction_count': len(instructions), 'simd_copy_instructions': len(simd),
        'pinned_opcode_checks': len(REQUIRED), 'status': 'static_contract_verified',
        'behavioral_parity': False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf', type=Path, required=True)
    p.add_argument('--disassembler', default=shutil.which('llvm-objdump') or 'llvm-objdump')
    p.add_argument('--json', type=Path)
    a = p.parse_args()
    result = verify(a.elf, a.disassembler)
    payload = json.dumps(result, indent=2, sort_keys=True)
    if a.json:
        a.json.write_text(payload + '\n')
    print(payload)


if __name__ == '__main__':
    main()
