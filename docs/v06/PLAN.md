# v0.6 implementation plan

Goal: independently test byte-BPE on the CPU-first runtime with runnable evidence.
Spec: docs/v06/DESIGN.md. Execution: inline, isolated extraction; no external writes.

- [x] 1. Tokenizer + dynamic model vocabulary. Files tools/byte_bpe.py,
  include/edgeai/ByteBPE.hpp, src/ByteBPE.cpp, Transformer* and export code.
  Tests first: exact 0..255 roundtrip, ranked merges/repeated pairs, Unicode,
  malformed merges, BOS, size guards, 513 logits and legacy exports.
- [x] 2. Data and protocol. Freeze installed sources before experimenting;
  tools/external_data.py, data/cpython_snapshot/, tests/test_external_data.py.
  Assert no cross-module splits, SHA verification, normalized near-duplicate
  detection and no evaluation data used by tokenizer.
- [x] 3. Native tools + cross-language contract. Tools for tokenization, evaluation
  and same-text benchmarking. Compare every token/logit, scalar and auto; ring wrap.
- [x] 4. Run six training trials and explicit task evaluation. Fixed CPU budget,
  independent seeds, predefined configs/selection, no test-based selection.
  Persist configuration, data/tokenizer hashes, losses, timings, native parities.
- [x] 5. Goal runner + release. Add independent quick/research profiles without
  removing legacy profiles. Test pipeline commands/errors. Release/portable/
  sanitizers, re-extract/rebuild, README/METAS/report, source checksums and ZIP.

Review focus: resource bombs in tokenizer/model loading; BOS counted as a byte;
misleading byte/tokens throughput; stale cache/checkpoint reuse; data leakage or
silent changes of benchmark corpus; unsupported platform claims.
