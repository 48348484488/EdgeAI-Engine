# v0.17 Portuguese Neural Baseline Design

## Purpose

v0.17 will turn the low-resource neural path from an untrained development fixture into a small, reproducibly trained Portuguese assistant. The target is useful short answers on inexpensive x86-64 computers without a discrete GPU. This release is a measured baseline, not a claim of general intelligence or parity with large language models.

## Scope

The release targets short Portuguese interactions in four bounded groups:

- greetings and conversational acknowledgements;
- concise definitions of common concepts;
- closed factual questions whose answers are represented in the licensed training corpus;
- short instructions that require a direct textual response.

Calculator, deterministic text transformations, bounded memory, and other exact operations remain outside the neural model. Their v0.16 tool score must not regress.

Long-form generation, source-code assistance, web retrieval, multilingual coverage, autonomous agents, and unrestricted question answering are out of scope.

## Success criteria

A candidate is accepted only if all of the following hold on the frozen v0.17 evaluation:

- neural human-review pass rate is greater than the v0.16 baseline of 0/20;
- deterministic tool accuracy remains 20/20;
- malformed or empty response rate does not exceed the v0.16 baseline;
- no accepted neural answer is copied from an evaluation prompt present in training;
- model file size is at most 16 MiB;
- canonical Linux peak process RSS is at most 64 MiB;
- the runtime uses no more than two CPU threads;
- canonical Linux cold startup is at most two seconds;
- inference is offline and the deployed binary has no Python dependency.

Results must report the number of reviewed prompts and the exact pass count. A percentage without the underlying count is insufficient.

## Architecture

The existing v0.16 focused C++ runtime remains the deployment foundation. v0.17 adds a trained checkpoint and a reproducible training-and-export path; it does not add a second inference engine.

The selected design is a compact instruction model specialized for Portuguese:

1. a byte-level BPE tokenizer trained only on the training split;
2. the existing small transformer format and native C++ backend;
3. response-only supervised training so prompt tokens do not dominate the loss;
4. post-training quantization using the existing mixed/int8/ternary representation when parity tests show that quality is preserved;
5. deterministic routing before neural inference.

Training may use Python and PyTorch in CI or a controlled training job. Deployment remains C++17 and CPU-only.

## Data and provenance

The v0.17 dataset is versioned under `data/portuguese_v017/`. Every source must have a recorded origin, license, retrieval or generation method, and content hash.

The initial dataset combines:

- deterministic, human-readable templates for bounded instruction behavior;
- small openly licensed Portuguese text sources suitable for redistribution;
- manually authored question-answer pairs committed in the repository.

Model-generated labels from external frontier APIs are not allowed in the initial baseline. Personal, private, scraped conversational, or license-unclear data are excluded.

The dataset generator produces immutable train, validation, and test manifests. The test split is generated and hashed before training. Exact prompts, normalized prompt variants, and answer-bearing records are checked for cross-split overlap. The tokenizer is trained on the training split only.

## Evaluation

Evaluation keeps deterministic and neural capability separate.

The frozen neural suite contains at least 40 prompts, balanced across the four scoped groups. Each record includes an ID, category, prompt, review rubric, and provenance. Exact-answer cases are scored automatically. Open responses default to failure until a human decision is recorded together with the SHA-256 hash of the exact response.

The evaluator records:

- pass count and rate by category;
- malformed and empty outputs;
- route correctness and neural-use flag;
- latency percentiles;
- exact generated text;
- checkpoint, corpus, tokenizer, and executable hashes.

A changed response invalidates its previous human approval. Validation results may select checkpoints; frozen test results may not.

## Training and checkpoint selection

Training is deterministic where supported and records seed, thread count, optimizer settings, step count, CPU time, wall time, token counts, loss curves, and artifact hashes.

At least three fixed seeds are compared under the same CPU-time or token budget. Checkpoint selection uses validation loss plus validation task results. The frozen test set is run only after the selection rule has chosen a checkpoint.

The first accepted release checkpoint must be reproducible from committed code, manifests, and declared dependencies. Large intermediate optimizer checkpoints are CI artifacts, not normal repository files.

## Runtime and failure behavior

v0.16 resource limits remain hard gates. The runtime validates the model before allocating the full working state. Unsupported format versions, oversized models, invalid tensor dimensions, incompatible tokenizer metadata, excessive state estimates, and prompt overflow fail with a nonzero exit status.

There is no silent fallback that presents an echo or untrained fixture as a trained neural answer. If the trained model is unavailable, deterministic routes may continue only when explicitly requested; neural requests must fail clearly.

## Repository changes

Expected additions are limited to:

- `data/portuguese_v017/` for manifests and redistributable data;
- a v0.17 training entry point under `benchmarks/` or `tools/`;
- export and parity validation for the selected checkpoint;
- `tests/` contracts for data separation, training metadata, native parity, and evaluation;
- `results/v017_portuguese/` for compact committed baseline reports;
- one active v0.17 workflow that uploads models and detailed evidence as artifacts;
- documentation updates after results exist.

Generated models, caches, optimizer states, and large raw corpora remain outside Git unless a small release checkpoint is intentionally approved for distribution.

## CI evidence

The v0.17 workflow has separate stages for data validation, bounded training, export, native parity, frozen evaluation, and resource enforcement. A build alone is never reported as neural success.

Artifacts include the selected model, tokenizer metadata, training report, evaluation records, process metrics, and a manifest binding every artifact to the source commit. Linux remains authoritative for the 64 MiB RSS gate; Windows provides functional and compatibility evidence.

## Risks and controls

- **Memorization:** sealed splits, overlap detection, and withheld templates.
- **Misleading quality claims:** exact counts, full responses, and human approvals bound to hashes.
- **Dataset licensing:** allowlisted sources and per-source provenance.
- **Quantization damage:** compare exported native output and evaluation against the selected training checkpoint.
- **CI overfitting:** fixed acceptance criteria and no checkpoint selection from frozen-test results.
- **Resource regression:** OS-observed RSS, startup, file-size, and thread gates on every candidate.

## Delivery sequence

1. Freeze the dataset schema, provenance rules, and evaluation corpus.
2. Establish an untrained v0.17 control using the current runtime.
3. Implement deterministic training and checkpoint reporting.
4. Export the selected checkpoint and verify Python/native parity.
5. Run frozen evaluation and human review.
6. Enforce low-resource limits and publish evidence.
7. Update README and changelog with only the claims supported by retained artifacts.
