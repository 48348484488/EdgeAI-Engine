# EdgeAI V25 — fail-closed 2048 main-call validation (2026-10-29)

The V24 PTY tests prove that four C++ candidates can run with injected callbacks, **not** that the original game has been rebuilt. This update closes two false-positive paths in the source-blind dependency auditor:

1. `generated_functions()` now requires a **function definition with a body**, not merely `extern "C" recovered_...();` declaration. The V23 `candidate_401758` semantic callback wrapper is not misreported as a native recovered export.
2. Optional `--elf` cross-checks every recorded direct `BL` site and destination against the **actual ELF instruction words**, and verifies the CFG binary SHA-256. Fabricated/missing/retargeted calls cause an error.
3. `--require-dependency-closure` exits with status 2 when internal calls are unresolved or indirect. `dependency_closure_complete` is **not** equivalent to strict linking, ABI validation, or QEMU parity; `complete` remains false.

The local V25 ELF auditor used the pinned stripped ARM64 game binary SHA-256
`a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b`.
It decoded **32 BL calls / 17 distinct targets** in `0x401758–0x401988`, including **30 internal** and **2 PLT** calls. The V24 ZIP includes native candidates for only **two** of the 15 distinct internal call targets; the other **13 providers are missing from that ZIP**, not necessarily missing from the V15 generated output. The semantic main candidate still injects callbacks for board mechanics.

Local V25 standalone audit: **8/8 tests passed**; V22/V24 PTY regressions: **5/5 passed**. Strict audit intentionally returned **exit code 2**. The existing private GitHub Actions run [#40909168647](https://github.com/48348484488/EdgeAI-Engine/actions/runs/40909168647) completed with a failed `verify` job, no assigned runner and no steps; the external CI failure cause remains unknown.

## Reproduction

```bash
python3 tools/edgeai_2048_call_closure.py \
  --cfg results/2048_main_cfg_v17.json \
  --generated-dir /path/to/real/v15/candidate_cpp \
  --expected-sha256 a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b \
  --elf /path/to/2048-arm64-stripped.elf \
  --require-dependency-closure \
  --output /tmp/2048_v25_call_closure.json

python3 -m unittest discover -s tests -p 'test_edgeai_2048_call_closure.py' -v
```

The next engineering gate is to regenerate/persist the 19 V15 C++ sources, replace the V24 mock callbacks with ABI-correct providers, link with `-Wl,-z,defs`, and run full-session differential tests against the ARM64 original in QEMU. Do not increase the verified 19/23 count until behavioral parity is established.
