# v0.7 implementation plan

Goal: real instruction + termination learning; preserve old runtime.
Spec: DESIGN.md. Method: inline execution requested by user, no extra confirmations.

1. Tokenizer/format: tests first for special IDs, text roundtrip, legacy file magic,
   malformed data and EOS output; extend ByteBPE Python/C++ and EDGEAI7 export/load.
2. Runtime: greedy selection masks only BOS/RESPONSE; EOS stops without emitting
   a byte; use same rule in native generator and chat; test early EOS and cap.
3. SFT data/training: freeze synthetic splits, hashes, masking and warmstart tests;
   implement preparation + response-only loss + safe checkpoint loading.
4. Experiments: same expanded before/after models, three seeds, fixed CPU budget;
   native exact/EOS scoring and all-logit parity, per-task/shift breakdown.
5. Executor: local instruction and instruction-quick profiles with failure logs.
6. Release: full tests, portable build, sanitizers, fresh ZIP rebuild; report both
   favorable and negative results; no claim of general conversation ability.

Review focus: final-target shift, padded gradients, accidental test overlap,
legacy file generation behavior, fabricated EOS from cap/empty decoded specials.
