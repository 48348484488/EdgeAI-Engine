# EdgeAI V24 — real PTY main-loop integration (host-only)

Date: 2026-10-29. Original 2048 ELF SHA-256: a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b.

## What changed

Added tests/test_2048_v24_main_pty.py to standard Python test discovery. It compiles four reconstructed C++ candidates together: V19 startup (0x401704), V20 SIGINT cleanup (0x4016ac), V21 terminal mode (0x4011cc), and V23 manually reconstructed main loop (0x401758).

Unlike V23's mocked input, V24 reads actual bytes from a Linux pseudo-terminal using getchar(), checks noncanonical/no-echo mode, and confirms exact terminal attributes are restored. Board and rendering helpers are deterministic STUBS, not the 19 recovered C++ functions.

## Tests executed locally

- Real key sequence A b R Q: move, spawn, undo, reset, quit. Checks event ordering, board snapshots, scores, and exact ANSI startup/restore output.
- Real key sequence ESC a B q: ignores unsupported keys, dispatches B, quits.
- Real SIGINT while blocked in getchar(): V20 cleanup, exact ANSI termination bytes, PTY restoration.

New V24 tests: 3/3 passed. Reran V22 real PTY tests: 2/2 passed. V23 deterministic host scenarios: 8/8 passed. V23 SHA-pinned ELF static contract: 140 instructions, 16 SIMD copies, 18 pinned opcode checks. These results do NOT prove ARM64/QEMU parity or complete-game execution.

## Reproduce on Linux with Python 3, g++ and glibc

    python3 -m unittest discover -s tests -p 'test_2048_v24_main_pty.py' -v

The test compiles its C++ harness in a temporary directory and removes it afterward.

## GitHub Actions blocker

The private GitHub Actions run https://github.com/48348484488/EdgeAI-Engine/actions/runs/40906053209 on commit 0a44c9b failed with zero job steps, runner_id=0, and zero billed Ubuntu runner milliseconds. The run completed in about four seconds. Multiple workflows failed similarly. The evidence indicates a failure before runner execution; it does NOT prove a code/test failure. Exact GitHub-side cause remains unconfirmed. V24 was tested locally, not in Actions.

## Remaining work

2048 function coverage stays at 19/23 validated. V19-V23 candidates still require direct comparison with original ARM64 under QEMU. Next link the 19 generated C++ helpers (not committed in this repository), reproduce complete game sessions under QEMU-AArch64 and compare stdout, board states and exit behavior. Do not treat deterministic helper stubs as recovered game logic.
