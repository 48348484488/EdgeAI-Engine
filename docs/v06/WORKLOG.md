# Worklog v0.6
Baseline: extracted supplied v0.5 ZIP into isolated v0.6 directory, preserving original.
Release CTest 9/9 and Python unittest 23/23 passed before edits.
Ruling: source archive retrieval unavailable (DNS + download tool failure); use
installed CPython 3.13.5 sources with exact hashes and local license. No claim
of equivalence to an upstream tag. This still provides data not authored here.
Review: training-cache identity originally lacked host identity; could misattribute
cached training times on another CPU. Added failing test, then platform/CPU/Python
and transitive training-module hashes. Rerun final six trials after this change.
Review: finite model weights alone do not ensure finite activations. Added a failing
C++ extreme-embedding regression, then fail explicitly on nonfinite output logits.
Compatibility: old CLI version test updated to v0.6; this was a version assertion,
not a functional regression. All old format and parity tests are retained.

## Checkpoint round-trip correction
Native full-logit verification rejected a TorchVersion class serialized in metadata. Added a failing safe-load regression and changed the metadata to a plain string. Kept weights_only=True; no arbitrary pickle loading or allowlist workaround. Source-hash identity invalidates the prior trials, so the six trials are re-executed, not silently relabeled.

## Final verification plan
Rebuild portable and sanitizer paths after the checkpoint regression; fresh release archive will be re-extracted and rebuilt, including Python and native contracts. Full and quick goal runs must both report all 12 stages passed. No published success until these gates complete.

## Final gates passed
Both independent profiles completed 12/12 stages. Release, portable and sanitizer suites passed: 10 CTest suites and 57 Python tests. Fresh extraction rebuilt and repeated tests/parity; shipped binary smoke tests passed. Final code, binaries, model and data bytes match that extracted archive. Six trained models scored zero of 28 diagnostic tasks each; deterministic calculator scored 12/12 separately. Joules unavailable. Full evidence and limits published, without frontier capability claims.
