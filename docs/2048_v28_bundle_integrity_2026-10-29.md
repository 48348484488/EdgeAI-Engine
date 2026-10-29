# EdgeAI V28 — verification of published 2048 C++ bundles

Date: 2026-10-29.

The V27 recovery script now creates **manifest schema v2** and hashes not only each C++ candidate, but also `coverage.json`, `native_link.json` and `recovered_candidates.so`. Before publishing the staging directory, it runs an **independent verifier**. The publication is atomic: on verification failure, the final directory is not created.

The verifier rejects missing or additional candidate files, symlinks, duplicate function addresses, changed bytes, an ELF hash mismatch, conflicting coverage/provenance, missing strict-link evidence and inconsistent native export rows. It does not mistake host-native linkage for ARM64 equivalence.

## Local tests

```sh
python3 -m unittest discover -s tests -p 'test_edgeai_2048*py' -v
# 16 tests (6 existing + 10 new), passed in the V28 local test run
```

## Verifying a generated bundle

```sh
python3 tools/edgeai_2048_bundle_verify.py /path/to/generated-bundle --elf /path/to/original-2048.elf
```

The ELF is pinned to SHA-256 `a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b` by the recovery script. To regenerate the real 19 providers, run `edgeai_2048_v15_recovery.py` with the **complete repository `tools/` directory** (including the multi-stage generator and its imports). The V27 ZIP is a partial offline bundle and lacks the generator. It is not proof of 19 regenerated files.

## Status and limits

- Local V28 tests: 16/16 passed, including 10 new tamper/provenance tests.
- The V27 partial ZIP still cannot regenerate the 19 providers without the full lifter dependency set. No full regeneration or new QEMU parity test occurred in V28.
- Existing historical behavioral coverage remains 19/23; V28 adds **artifact integrity**, not function recovery.
- GitHub Actions #40951576873 (Linux/Windows) and #40951576852 (`verify`) failed **before any step**, with 0 ms billed runtime. This is a pre-execution CI problem, not evidence of a code crash. Root cause not established.
