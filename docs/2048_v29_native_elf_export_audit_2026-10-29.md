# EdgeAI V29 — audit native ELF exports against the published C++ bundle

Date: 2026-10-29.

## Problem fixed

V28 checked the SHA-256 of `recovered_candidates.so` and the `native_link.json` assertions, but a replaced library **plus a recomputed manifest** could still pass verification even if the shared library did not export the recovered functions. The test fixture even used a non-ELF byte string for its library.

V29 inspects the actual compiled shared library using `nm -D`. It requires that every `recovered_<address>` from the candidate manifest is defined as a global text symbol (`T`/`W`), that no extra recovered function is defined, and that no `recovered_*` reference remains unresolved. It rejects non-ELF files and unavailable/failing symbol inspection. Existing SHA-256 and provenance gates remain in force.

The synthetic V15 fixture now compiles an actual ELF shared library with `g++ -shared -fPIC -Wl,-z,defs`, instead of writing fake library bytes.

## Local evidence

```
python3 -m unittest discover -s tests -p 'test_edgeai_2048*py' -q
Ran 21 tests ... OK
```

Five additional negative/positive tests cover valid native exports, missing exports with a recomputed manifest, extra exports, non-ELF bytes, and unresolved internal recovered-function references. The 16 existing V27/V28 tests also pass.

This **does not** mean the 19 providers were regenerated in this run. The test is against a synthetic 2-function fixture. It is an integrity and linkage check, **not** proof of ARM64 behavioral equivalence, original source recovery, or a complete playable 2048. Historical coverage remains 19/23.

## Stalled CI

GitHub Actions run [#40951639163](https://github.com/48348484488/EdgeAI-Engine/actions/runs/40951639163) failed before any job step; the job's steps array was empty and the billing API showed 0 ms. The log endpoint returned `404 BlobNotFound`. The root cause of the pre-execution failure is not established.
