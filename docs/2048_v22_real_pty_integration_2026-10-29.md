# EdgeAI V22 — real Linux PTY integration for the 2048 lifecycle

**Date:** 2026-10-29. **Scope:** experimental candidates from V19 (startup `0x401704`), V20 (SIGINT cleanup `0x4016ac`), and V21 (terminal mode `0x4011cc`).

## New result

Compiled the three independently recovered C++ candidates into a single x86_64 host executable with **real glibc calls**, not mocked `tcgetattr`, `tcsetattr`, or `__printf_chk`. A Python harness creates a Linux pseudo-terminal, launches the executable, observes terminal flags after startup, sends `SIGINT`, and verifies that the terminal state is fully restored.

Two scenarios passed locally:

1. Startup → enter terminal mode → SIGINT → cleanup → restore.
2. Startup → restore → enter terminal mode again → SIGINT → cleanup → restore.

Both verify exit code 0, exact stdout escape sequence and termination text, unchanged non-`c_lflag` termios fields, expected clearing of bitmask `0xA` during gameplay, and byte-for-byte restored Python termios attributes at shutdown.

**Local result:** 2/2 new PTY tests passed; 15/15 pre-existing V21 tests also passed. The original ELF checksum remained `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`.

## Reproduce

On Linux with glibc, Python 3.11+ and a C++17 compiler:

```sh
python3 -m unittest -v experiments/2048_v22/test_2048_pty_integration.py
```

This test does not need a physical phone, root, or a real terminal window. It does require a working PTY device.

## What this does **not** establish

- No direct differential comparison with original ARM64 function execution under QEMU was performed in V22.
- This is not an end-to-end playable reconstruction of 2048.
- The 19/23 ARM64-validated function count is **unchanged**. V19–V21 remain experimental despite stronger integration evidence.
- `tcgetattr` failure in the V21 candidate follows an undefined-data path present in the original; the PTY tests cover the successful system-call path only.
- The private EdgeAI GitHub Actions `verify` job remains failed with no exposed steps in run [#40833068993](https://github.com/48348484488/EdgeAI-Engine/actions/runs/40833068993). Local tests are not a substitute for CI.

## Next

Execute these lifecycle paths against the original ARM64 ELF under QEMU with controlled `termios` calls; compare observable calls and terminal state. Then integrate the main function `0x401758` and validate the complete game loop.
