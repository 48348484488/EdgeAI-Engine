# EdgeAI V21 — 2048 terminal-state manager (29 October 2026)

**Status: experimental candidate; original ARM64/QEMU parity NOT established.**

The stripped 2048 ELF (SHA-256 `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`) was inspected at `0x4011cc..0x4012d0` (65 AArch64 instructions, 260 bytes). Instruction SHA-256: `882ba336dfe89eefd365a96414dcb37e6fa8eb494be83dc4a7306e48fd92be0a`.

The new candidate `experiments/2048_v21/candidate_4011cc.cpp` reconstructs the observed terminal-state transitions: initial flag 1 from `.data[0x420080]`, a 60-byte saved termios structure at `.bss[0x420090]`, `tcgetattr(0,...)`, copying the original termios, clearing `c_lflag` bits `0xA`, `tcsetattr(0,0,...)`, and restoring the saved state and the escape `ESC[?25hESC[m`. It links against the V19 startup candidate and is callable by the V20 signal handler.

**Local verification:** 15/15 Python tests passed, including SHA pinning, mutation rejection, strict C++ compilation, mocked termios state transitions, and a linked V19 startup + V21 terminal execution test. The separate committed host regression test can be run on a Linux host with:

```sh
clang++ -std=c++17 -Wall -Wextra -Werror \
  experiments/2048_v21/candidate_4011cc.cpp \
  experiments/2048_v21/test_terminal_host.cpp \
  -o /tmp/edgeai-2048-terminal && /tmp/edgeai-2048-terminal
```

**Limits:** The original ARM64 function has a stack canary and SIMD copies. The C++ candidate models the normal termios data flow, not instruction-level stack behavior. The original ignores `tcgetattr` failures and may then read uninitialized stack data; the candidate does not establish parity on that path. Host tests use mocked libc and do not prove ARM64 parity. This candidate does **not** increase validated coverage beyond 19/23 functions. Main loop `0x401758` and full executable integration remain outstanding.

**CI:** Private run [#40833068993](https://github.com/48348484488/EdgeAI-Engine/actions/runs/40833068993) still reports failed `verify` with zero exposed steps; job logs return 404 BlobNotFound. The root cause is not established. Local testing is functioning.

A separate V21 reproduction ZIP contains the bounded Python lifter, 15 Python tests, original ELF, generated candidate, JSON report and V19/V20 candidate files.
