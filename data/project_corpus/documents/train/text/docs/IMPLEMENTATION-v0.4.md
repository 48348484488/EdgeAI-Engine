# Selective precision implementation plan

Goal: add mixed-precision inference and test memory sensitivity.
Spec: docs/DESIGN-v0.4.md
Execution: inline in an isolated copy of the supplied v0.3 ZIP; original untouched.

Global constraints: C++17, CPU only, backward model reading, one thread in measurements,
FP32 activations/state, explicit null energy when unavailable, no untested model claims.
Review focus: odd matrix sizes; unknown dtype; malformed/truncated models; all-zero
quantized rows; train/runtime equations and causal state parity.

1. Tests first: Python policy, gradient and export contracts; native matrix arithmetic,
   all dtype round-trips and invalid payloads. Capture missing-feature failures.
2. Implement MixedHybrid Python reference and typed EDGEAI4 exporter; keep legacy exporter.
3. Implement Int8Matrix + MixedMatrix and kernels, integrate HybridModel/Backend/inspect.
4. Run all old and new tests; Python/C++ parity for odd shapes and all precision policies.
5. Freeze benchmark protocol before final runs. Same initialization and batches per seed;
   final fixed step, independent test set, all policy outcomes reported. Include reference
   Transformer with explicit parameter mismatch. Save checkpoints and raw JSON.
6. Train/export an educational byte demo; measure native full forward on same token stream
   and report weight bytes, file bytes, RSS, wall and CPU time separately from quality.
7. Release, portable and sanitizer suites; fresh ZIP extraction/build; SHA256 manifest.
