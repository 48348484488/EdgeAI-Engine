# Review record

Inline self-review; no independent reviewer agent was available or claimed.

- Correctness: rank ordering and duplicate BPE spellings; BOS semantics; all 256
  bytes; invalid UTF-8 rendering separate from raw model feedback; ring wrap;
  legacy format behavior. Verified with Python/C++ all-logit tests.
- Data: module-level split; original bytes and source licenses retained; manifest
  tamper and cross-family leakage tests; near-duplicate filter checked on a changed
  identifier. Semantic similarity and shared Python idioms can remain.
- Metrics: score the same raw blocks; BOS not a byte; token accuracies not compared
  across vocabularies; report tokenization overhead and larger BPE vocabulary head.
- Security: reject malformed model and raw block lengths; no shell/exec/eval for
  generated code. Code diagnostic accepts only bounded arithmetic ASTs.
- Fixed in review: nonfinite activations can arise from finite extreme weights;
  added rejection and regression. Host identity needed in reusable training records;
  added host/dependency identity and reran final experiments.
- Limitations: tokenizer is intentionally small, not a production tokenizer for
  huge adversarial inputs; dynamic adaptive reasoning and frontier generalization
  remain absent; training and RAPL energy claims are separated.

- Checkpoint round trip: TorchVersion metadata was a custom pickle type rejected by
  weights_only loading. Converted it to plain str, added a regression and reran
  all six trials under the new source identity; unsafe deserialization remains off.
