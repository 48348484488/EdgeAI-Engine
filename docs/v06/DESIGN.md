# v0.6: independent data and tokenization experiment

## Intent and limits
CPU-only native inference for weak PCs. Advance measurable quality/compute, not
an untested claim of frontier capability. Preserve all earlier model formats.
User explicitly authorized routine engineering without permission checkpoints.

## Design chosen before training
1. Reversible byte-BPE in Python and C++17, fixed byte categories, no normalization,
   all 256 bytes plus learned merges and one BOS. Train merges only on train files.
   BPE is known technology, not a new architecture. Cap pieces at 64 bytes, vocab
   at 4096; validate merge dependencies and reject duplicate/ambiguous definitions.
2. EDGEAI6 embeds tokenizer and dynamic vocabulary. EDGEAI5 remains byte-only.
   Inference masks BOS after prefill, treats decoded bytes consistently, retains
   raw token IDs in feedback, and renders invalid UTF-8 safely.
3. Freeze independently authored CPython stdlib files from the installed runtime,
   including license, copyright, interpreter/package version, path and SHA256.
   Direct network download was unavailable; do NOT claim official-release byte
   identity or a verified git revision. Bundle exact unmodified snapshots.
   Group by module; do not scatter a module into train/valid/test.
4. Evaluation blocks: same raw byte blocks for both models, BOS scores every byte,
   reject normalized near duplicates against earlier splits. Report canonical
   token-sequence NLL / raw bytes / ln(2), not token accuracy as intelligence.
   This is one project/domain, English comments + Python, not diverse language data.
5. Compare byte+BOS vs 256-merge BPE+BOS, W8A32, approx matched parameter counts,
   3 seeds, 20 CPU seconds each, one thread, sequence 64 tokens, AdamW lr .002,
   batch 8. Validation at 25/50/75/100% budget and final checkpoint chosen there.
   More bytes/context per BPE token is an intentional system tradeoff; not an
   architecture-isolation study. Include preprocessing and end-to-end costs.
6. Native benchmark uses the SAME raw held-out texts including tokenizer cost;
   include model load, raw prefill and greedy generation, RSS, file bytes. Joules
   must remain null without a real sensor. No weak-PC or Windows claims.
7. Add small held-out useful-task check: arithmetic answers, short constrained
   code completions/instructions, assessed explicitly and separately from NLL.
   No shell execution or arbitrary generated-code execution in the evaluator.

## Exit criteria
Old suites green; new roundtrip/error/future-token/serialization tests green;
Python/C++ token IDs and all logits agree on legacy and new models including long
sequences; data integrity/tamper/near-duplicate tests; all six training runs and
native reports; full offline goal cycle; portable and sanitizer builds; extracted
ZIP rebuilt and tested. Record incomplete capabilities rather than infer them.
