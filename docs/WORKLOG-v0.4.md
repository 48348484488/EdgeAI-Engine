# v0.4 execution record

- Baseline: supplied v0.3 ZIP extracted into independent v0.4 directory; six original CTest suites pass in Release.
- Decision: add weight-only INT8 between FP32 and ternary rather than changing recurrence again. Activations/state remain FP32.
- Decision: preserve historical results in results-v0.3; new results must be measured in this session.
- Review focus: unknown dtype and row-scale errors must fail before execution; compare all logits, not generated samples alone.
- Python precision tests were red before implementation, then six tests passed.
- Native mixed matrix test failed on the missing feature, then arithmetic/serde checks passed.
- Added runtime CLI CPU metric and rejected numeric suffix/unknown kernel after two red tests.
- Primary benchmark completed all 21 runs; fixed protocol, same master and batch hashes.
- INT8/FP32 memory supports substantially more recall than all-ternary in this micro-task.
- Separate output PTQ used frozen checkpoints; all three seeds reported without retraining.
- Native size reduction was not a native speedup; peak RSS did not resolve weight-size changes.
- Energy counters unavailable; raw result preserves null joules.
- Review: self-review of source/data contracts; no independent subagent/human review or old-PC certification.
- Package integrity checked against SHA256SUMS after extraction; independent-folder build and all eight CTest suites passed. Shipped Linux binary calculator smoke test returned 181907.
