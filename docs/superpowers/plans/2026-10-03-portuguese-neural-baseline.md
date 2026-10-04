# v0.17 Portuguese Neural Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train, export, and evaluate a genuinely useful compact Portuguese instruction model that runs in the existing C++ low-resource runtime.

**Architecture:** Keep deterministic routing and the v0.16 C++ inference engine unchanged wherever possible. Add a sealed, licensed Portuguese dataset; response-only PyTorch training; native export/parity verification; frozen human-review evaluation; and CI evidence that binds quality and resource results to exact artifacts.

**Tech Stack:** Python 3, PyTorch CPU, C++17, CMake, unittest, GitHub Actions, existing EDGEAI8 transformer/BPE format.

**Spec:** `docs/superpowers/specs/2026-10-03-portuguese-neural-baseline-design.md`

## Global Constraints

- Deployment is offline, CPU-only C++17 with no Python runtime dependency.
- Model file size is at most 16 MiB.
- Canonical Linux peak process RSS is at most 64 MiB.
- Runtime uses one or two CPU threads.
- Canonical Linux cold startup is at most two seconds.
- Neural human-review pass count must exceed the v0.16 baseline of 0/20.
- Deterministic tool accuracy must remain 20/20.
- Empty or malformed response rate must not exceed the v0.16 baseline.
- External frontier-model labels, private data, and license-unclear sources are forbidden.
- Frozen-test results cannot select checkpoints.
- Open neural responses fail until a human decision is bound to the exact response SHA-256.

## Review Focus

- UTF-8 prompts with composed/decomposed accents must normalize consistently; Task 1 pins normalization and hashing.
- Duplicate or near-duplicate prompts crossing train/test must be rejected; Task 1 pins normalized overlap detection.
- Missing or non-allowlisted source licenses must fail data generation; Task 1 pins provenance validation.
- Quantization or native export that changes selected-token logits beyond tolerance must fail; Task 4 pins parity thresholds.
- A trained model that exceeds file, state, RSS, startup, or thread limits must be rejected rather than silently substituted; Tasks 5 and 6 pin runtime and CI failure behavior.

---

### Task 1: Licensed Portuguese dataset and sealed splits

**Files:**
- Create: `tools/portuguese_data_v017.py`
- Create: `data/portuguese_v017/sources.json`
- Create: `data/portuguese_v017/NOTICE.md`
- Create: `tests/test_portuguese_data_v017.py`
- Generate: `data/portuguese_v017/{train,valid,test}.jsonl`
- Generate: `data/portuguese_v017/manifest.json`
- Modify: `.gitattributes`

**Interfaces:**
- Produces: `normalize_text(value: str) -> str`, `validate_sources(rows: list[dict]) -> None`, `build_dataset() -> dict[str, list[dict]]`, and `write_dataset(root: pathlib.Path) -> dict`.
- Dataset rows contain `id`, `category`, `prompt`, `response`, `source_id`, and `license`.

- [ ] **Step 1: Write failing provenance, Unicode normalization, stable-ID, deterministic-generation, and normalized cross-split-overlap tests in `tests/test_portuguese_data_v017.py`.**

Assert that missing licenses fail, `ação` and its decomposed form normalize identically, duplicate normalized prompts across train/test fail, two builds are byte-identical, and test prompts are absent from tokenizer/training input.

- [ ] **Step 2: Run the dataset tests and verify failure because `portuguese_data_v017` does not exist.**

Run: `python -m unittest tests.test_portuguese_data_v017 -v`  
Expected: import failure for the missing module.

- [ ] **Step 3: Implement the dataset module and source registry.**

Use NFC Unicode normalization, sorted JSON keys, LF line endings, SHA-256 IDs, an explicit license allowlist, and deterministic split assignment. Initial categories are `greeting`, `definition`, `closed_fact`, and `short_instruction`.

- [ ] **Step 4: Generate the files and verify tests plus manifest hashes.**

Run: `python tools/portuguese_data_v017.py --out data/portuguese_v017 && python -m unittest tests.test_portuguese_data_v017 -v`  
Expected: all tests pass and regeneration leaves no diff.

- [ ] **Step 5: Commit the sealed data contract.**

`git commit -m "feat: add sealed Portuguese v0.17 dataset"`

### Task 2: Frozen quality evaluator and review ledger

**Files:**
- Create: `tools/evaluate_portuguese_v017.py`
- Create: `tests/test_evaluate_portuguese_v017.py`
- Create: `data/portuguese_v017/review.json`
- Create: `results/v017_portuguese/control.json`

**Interfaces:**
- Consumes: v0.17 test rows from Task 1 and JSON lines emitted by `edgeai_low_resource_cli`.
- Produces: `score_record(item: dict, response: dict, reviews: dict) -> dict`, `summarize(records: list[dict]) -> dict`, and a report with exact counts, category totals, full outputs, and artifact hashes.

- [ ] **Step 1: Write failing tests for exact answers, default-fail human review, response-hash invalidation, empty output, wrong route, category counts, and refusal to use test results for checkpoint selection.**

- [ ] **Step 2: Run the evaluator tests and verify the missing-module failure.**

Run: `python -m unittest tests.test_evaluate_portuguese_v017 -v`

- [ ] **Step 3: Implement evaluator functions and CLI.**

CLI arguments: `--binary`, `--model`, `--corpus`, `--manifest`, `--reviews`, `--output`, and optional `--compare-control`. Never mutate the review ledger.

- [ ] **Step 4: Generate an untrained control report using the v0.16 fixture and commit only compact JSON evidence.**

Expected control: tool score stays separate; neural approvals remain zero unless exact responses already have valid review hashes.

- [ ] **Step 5: Run tests and commit.**

`git commit -m "feat: add frozen Portuguese quality evaluation"`

### Task 3: Deterministic response-only CPU training

**Files:**
- Create: `benchmarks/portuguese_v017.py`
- Create: `tests/test_portuguese_training_v017.py`
- Reuse: `tools/byte_bpe.py`
- Reuse: existing transformer/export helpers used by v0.7-v0.15 training

**Interfaces:**
- Consumes: Task 1 train/valid splits only.
- Produces: `train_candidate(config: TrainConfig, seed: int) -> CandidateReport`; checkpoint files; and `training.json` containing seeds, token counts, CPU/wall time, loss curves, validation metrics, dependency versions, and hashes.
- `TrainConfig` fixes model dimensions, tokenizer vocabulary ceiling, context window, optimizer, response-only mask, thread count, step/token budget, and three seeds.

- [ ] **Step 1: Write failing tests for response-only loss masks, tokenizer train-only input, deterministic batch order, equal seed budgets, finite losses, resume metadata validation, and validation-only checkpoint selection.**

- [ ] **Step 2: Run tests and verify they fail before implementation.**

Run: `python -m unittest tests.test_portuguese_training_v017 -v`

- [ ] **Step 3: Implement the smallest training pipeline that reuses the current transformer equations and EDGEAI8 exporter.**

Default quick profile uses one seed and a tiny budget for tests. Release profile uses seeds 11, 22, and 33 under identical token budgets and no more than two threads.

- [ ] **Step 4: Run quick training twice and verify deterministic report fields and artifact hashes.**

Run: `python benchmarks/portuguese_v017.py --profile quick --threads 1 --out build/v017-quick` twice in clean output directories.

- [ ] **Step 5: Run all training unit tests and commit.**

`git commit -m "feat: train compact Portuguese instruction model"`

### Task 4: Export and Python/native parity gate

**Files:**
- Create: `tools/verify_portuguese_v017.py`
- Create: `tests/test_verify_portuguese_v017.py`
- Modify only if required by a demonstrated incompatibility: `tools/train_tiny.py`, `src/TransformerModel.cpp`, `include/edgeai/TransformerModel.hpp`

**Interfaces:**
- Consumes: one validation-selected Task 3 checkpoint and tokenizer.
- Produces: one EDGEAI8 `.edge` model plus `parity.json`.
- `compare_logits(reference, native, atol: float, rtol: float) -> dict` reports maximum error and the first mismatching token.

- [ ] **Step 1: Write failing tests for artifact binding, tokenizer metadata, output dimensions, corrupt checkpoints, and a parity failure when quantization changes selected-token order or exceeds declared tolerance.**

- [ ] **Step 2: Run tests and confirm the missing verifier failure.**

- [ ] **Step 3: Implement export verification using fixed validation prompts, predeclared tolerances, and native `edgeai_token_logits` output.**

Do not change model format unless the current format cannot represent the selected trained checkpoint and a failing compatibility test proves it.

- [ ] **Step 4: Build native tools and run quick checkpoint parity.**

Run: `cmake -S . -B build-v017 -DCMAKE_BUILD_TYPE=Release && cmake --build build-v017 -j2 && python tools/verify_portuguese_v017.py --build build-v017 --checkpoint build/v017-quick/selected.pt --out build/v017-parity`  
Expected: tokenizer/hash checks pass and logits stay within the declared tolerance.

- [ ] **Step 5: Commit.**

`git commit -m "feat: verify Portuguese checkpoint native parity"`

### Task 5: Trained-model runtime acceptance

**Files:**
- Modify: `tests/test_low_resource_engine.cpp`
- Create: `tests/test_portuguese_runtime_v017.py`
- Modify if tests require it: `src/LowResourceEngine.cpp`, `examples/low_resource.cpp`

**Interfaces:**
- Consumes: exported model and manifest from Task 4.
- Produces: unchanged CLI JSON schema with `route`, `neural_used`, and `text`; nonzero exits for incompatible or oversized artifacts.

- [ ] **Step 1: Add failing tests for Portuguese UTF-8 prompts, trained-model loading, prompt limit, model/state preflight, missing model, incompatible tokenizer metadata, and no echo/untrained fallback.**

- [ ] **Step 2: Run focused runtime tests and capture the expected failures.**

- [ ] **Step 3: Make only the runtime changes required by the failing acceptance tests.**

Preserve the 16 MiB model, 64 MiB estimated working-set, 4096-byte prompt, and two-thread hard limits.

- [ ] **Step 4: Run focused C++ and Python runtime tests.**

Run: `ctest --test-dir build-v017 -R 'edgeai_(bounded_memory|low_resource_engine)' --output-on-failure && python -m unittest tests.test_portuguese_runtime_v017 -v`

- [ ] **Step 5: Commit.**

`git commit -m "feat: accept trained Portuguese low-resource model"`

### Task 6: Reproducible v0.17 CI and retained evidence

**Files:**
- Create: `.github/workflows/portuguese-v017.yml`
- Create: `tests/test_portuguese_workflow_v017.py`
- Modify: `scripts/measure_low_resource.py`

**Interfaces:**
- Consumes: Tasks 1-5.
- Produces: data-validation, quick-training, release-training, export/parity, frozen-evaluation, Linux-budget, and Windows-functional jobs; uploaded model and evidence manifest.

- [ ] **Step 1: Write failing workflow-contract tests.**

Assert read-only default permissions, pinned dependency versions, maximum two threads, sealed-data validation before training, validation-only selection, parity before evaluation, `/usr/bin/time -v` RSS measurement, all hard gates, and `if: always()` evidence upload.

- [ ] **Step 2: Run workflow tests and verify failure because the workflow is absent.**

- [ ] **Step 3: Implement the workflow with quick checks on pushes and bounded release training on manual dispatch.**

The release job must upload rather than commit model binaries. Its evidence manifest binds source SHA, dataset, tokenizer, checkpoint, exported model, executable, and reports.

- [ ] **Step 4: Extend resource measurement tests for oversized model, RSS above 64 MiB, startup above two seconds, threads above two, and missing OS RSS data.**

- [ ] **Step 5: Run workflow and measurement tests, then commit.**

`git commit -m "ci: verify Portuguese v0.17 training and runtime"`

### Task 7: Release candidate evaluation and honest documentation

**Files:**
- Create after an actual release run: `results/v017_portuguese/training.json`
- Create after an actual release run: `results/v017_portuguese/parity.json`
- Create after human review: `results/v017_portuguese/evaluation.json`
- Modify: `data/portuguese_v017/review.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Create: `docs/portuguese-v017.md`

**Interfaces:**
- Consumes: retained release artifacts from Task 6.
- Produces: reviewed baseline with exact pass counts and hashes; concise reproduction instructions and limitations.

- [ ] **Step 1: Run the release workflow and download its evidence artifacts without changing acceptance criteria.**

- [ ] **Step 2: Review every open neural response and record decisions bound to exact response SHA-256 values.**

Do not approve malformed, evasive, factually wrong, or rubric-violating answers.

- [ ] **Step 3: Re-run evaluation with the completed review ledger.**

Acceptance requires neural passes greater than 0/20, tools exactly 20/20, no malformed regression, parity success, model at most 16 MiB, RSS at most 64 MiB, startup at most two seconds, and at most two threads.

- [ ] **Step 4: If any gate fails, publish the failed evidence as an experiment and do not label v0.17 successful. If all gates pass, update documentation with exact counts and limitations.**

- [ ] **Step 5: Run the complete C++ and Python suites plus `git diff --check`, then commit compact evidence and documentation.**

`git commit -m "docs: record verified v0.17 Portuguese baseline"`

### Task 8: Whole-branch review and integration

**Files:**
- Review every changed file against the spec and this plan.

**Interfaces:**
- Consumes: completed Tasks 1-7.
- Produces: review findings, corrected branch, final green CI, and a pull request; no automatic merge.

- [ ] **Step 1: Run the full native suite, full Python discovery, focused v0.17 evaluation, and resource gates from a clean checkout.**

- [ ] **Step 2: Verify repository hygiene.**

Confirm no optimizer checkpoints, caches, raw unlicensed corpora, generated build trees, or unreviewed model binaries are tracked.

- [ ] **Step 3: Request an independent whole-branch review focused on leakage, evaluation honesty, native parity, and resource enforcement.**

- [ ] **Step 4: Fix every important finding with a failing test first and rerun all affected gates.**

- [ ] **Step 5: Push the reviewed branch and create a PR to `main` containing exact evidence links and no unsupported capability claims.**
