# EdgeAI V30 — same-toolchain native rebuild attestation

Date: 2026-10-29.

## Confirmed weakness

V29 verified SHA-256, metadata, and the actual dynamic symbol names of `recovered_candidates.so`. A replacement ELF exporting the **same** `recovered_<address>` symbols but implementing different behavior could still pass if the bundle manifest hash was recomputed. A regression test reproduces this false positive using two deliberately wrong C++ function bodies.

## Change

`edgeai_2048_bundle_verify.py --rebuild-native` recompiles the published C++ candidates using the V15 generator's exact host compiler flags (`g++ -std=c++17 -O2 -fPIC -shared -Wl,-z,defs`) and **the original `coverage.json` function order**, then compares the resulting shared library SHA-256 against the published ELF. It rejects mismatched native code even if all exported names and manifest hashes agree. The recovery driver now requires this check before atomically publishing a bundle.

The check is opt-in for standalone verification because identical output requires the same compiler/linker toolchain and compatible build environment. The recovery driver always opts in. The synthetic V15 fixture now uses the same build flags. The bundle test suite reuses a single compiled fixture, avoiding repeated redundant builds in each case.

## Evidence

Local command: `python3 -m unittest discover -s tests -p 'test_edgeai_2048*py' -q`.

Result: **23 tests passed** in **9.64 seconds** in this container. The two new cases verify successful reproducibility and reject a re-hashed library with identical exports but incorrect machine code. The previous V29-only verification accepts that deliberately forged ELF, demonstrating the gap. No test hung locally.

GitHub Actions [#40958658116](https://github.com/48348484488/EdgeAI-Engine/actions/runs/40958658116) remains failed before executing any step; the job's steps field is null. This does **not** establish that the EdgeAI test code hung; the external pre-execution failure has no confirmed root cause.

## Limitations

This is a source-to-binary reproducibility check, not ARM64 behavioral equivalence. It cannot prove that the reconstructed C++ is faithful to the original game; it only proves that the published native `.so` matches the supplied candidate sources on the same toolchain. The original 19 ARM64 functions were **not regenerated in this run**. Historical coverage remains **19/23**. The next substantive task is to run the V15 regeneration with its complete lifter modules and compare the resulting game sessions against the original ARM64 in QEMU.
