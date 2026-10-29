# EdgeAI V23 — 2048 main-loop candidate (not QEMU validated)

Date: 2026-10-29. Original AArch64 ELF SHA-256: a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b.

## New work

The file candidate_401758.cpp is a manually transcribed, source-blind host-side semantic candidate for the ARM64 main loop 0x401758–0x401988. It is NOT automatically lifted, byte-identical source recovery, original ARM64 runtime parity, or a complete game executable.

It models a 64-byte board, a 64-byte undo snapshot, score, R/r reset, lowercase b undo, Q/q quit, ESC ignore, A/B/C/D movement, tile spawning, and both terminal conditions. It uses injected hooks for helper functions that still need linking. A bounded read count exists only to make host tests terminate; the original keyboard loop is unbounded.

The file test_main_candidate.cpp exercises eight deterministic scenarios using mock callbacks for unlinked helper functions. It does not prove equivalence with the original ARM64 runtime.

The file verify_main_elf.py validates the SHA-pinned original ELF using llvm-objdump, 140 contiguous instructions, 16 SIMD copy instructions, and 18 pinned opcode/operand checks. A modified ELF was rejected in a negative test. This is a static contract, not behavioral parity.

## Reproduction

~~~sh
python3 verify_main_elf.py --elf /path/to/2048.elf --json v23_static_contract.json
g++ -std=c++17 -O2 -Wall -Wextra -Werror -pedantic test_main_candidate.cpp -o test_main_candidate
./test_main_candidate
~~~

Optional sanitizer build:

~~~sh
g++ -std=c++17 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer test_main_candidate.cpp -o test_main_candidate_san
./test_main_candidate_san
~~~

## Local results

- 8/8 main-loop scenario checks passed, including an AddressSanitizer/UBSan run.
- ELF static contract passed: 140 instructions, 16 SIMD copies, 18 pinned opcodes, SHA-256 match.
- 1/1 negative hash test passed: tampered ELF rejected.
- V22 real-PTY regressions: 2/2 passed.
- Private GitHub Actions verify job remains failed with no steps exposed; tests above ran locally.

## Remaining blockers

Connect the candidate to the 19 validated helper functions and V19/V20/V21 startup/terminal routines with correct ABI and state sharing. Then compare scripted terminal sessions against the original ARM64 ELF under QEMU. QEMU-AArch64 and its userspace were unavailable in this local environment. The confirmed behavioral count stays 19/23; the main loop is an experimental candidate, not a newly validated function.
