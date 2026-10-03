# EdgeAI v0.16 Low-Resource Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a real, offline, CPU-only EdgeAI runtime for weak, inexpensive x86-64 PCs, with hard resource budgets, honest task-quality measurements, and no dependency on Python at runtime.

**Architecture:** Add an opt-in `EDGEAI_LOW_RESOURCE` build profile and a narrowly composed runtime. The profile keeps deterministic routing/tools, bounded persistent memory, and exactly one neural backend; excludes Android/JNI, code search, development utilities, and unused model backends. A dedicated CLI validates its model before loading, emits machine-readable metrics, and preserves the existing full build unchanged.

**Tech Stack:** C++17, CMake/CTest, existing EdgeAI transformer/int8 primitives, Python 3 only for development evaluation and CI harnesses, GitHub Actions on Ubuntu and Windows.

**Spec:** `docs/superpowers/specs/2026-10-03-low-resource-runtime-design.md`

## Global constraints

- The low-resource process must stay at or below 64 MiB peak RSS on the canonical Linux CI workload.
- The loaded model file must stay at or below 16 MiB.
- Inference must use at most two CPU threads.
- Cold startup must finish in at most 2 seconds on the canonical Linux CI runner; this is a regression gate, not a claim about every PC.
- The shipped low-resource executable must run fully offline and without Python.
- Existing default targets and behavior must remain available and unchanged.
- Tool-route results and neural-route results must be reported separately.
- A build, a passing smoke test, and useful neural answers are distinct claims.

## Review focus

Before implementation, challenge these failure modes:

1. The focused binary accidentally links excluded components through the existing monolithic library.
2. Memory is bounded in RAM but the persistence file or temporary allocations remain unbounded.
3. An oversized or corrupt model allocates memory before validation fails.
4. Internal accounting passes while actual OS peak RSS exceeds the budget.
5. Aggregate quality hides a neural regression behind correct calculator/tool answers.

## Task 1: Add the focused build profile and composition test

**Files:**
- Modify: `CMakeLists.txt`
- Create: `tests/test_low_resource_composition.py`

- [ ] Write a failing composition test that configures `-DEDGEAI_LOW_RESOURCE=ON`, builds `edgeai_low_resource_cli`, inspects the generated target metadata or link map, and rejects `CodeSearch.cpp`, Android/JNI sources, `HybridBackend.cpp`, `EdgeModel.cpp`, and `TernaryBackend.cpp`.
- [ ] Run `python tests/test_low_resource_composition.py --source . --build build-low-resource` and confirm it fails because the profile/target does not exist.
- [ ] Add the `EDGEAI_LOW_RESOURCE` CMake option.
- [ ] Define a dedicated `edgeai_low_resource` library from an explicit source allowlist: router, calculator, text tools, bounded memory, low-resource engine, backend interface, byte tokenizer, transformer model/backend, mixed matrix, int8 kernel, ternary primitives, and kernels.
- [ ] Add `edgeai_low_resource_cli` and keep the existing `edgeai` library and targets unchanged when the option is off.
- [ ] Export a deterministic link map or CMake source manifest for the composition test.
- [ ] Re-run the composition test and normal configure/build tests:
  - `python tests/test_low_resource_composition.py --source . --build build-low-resource`
  - `cmake -S . -B build-default -DEDGEAI_BUILD_TESTS=ON`
  - `cmake --build build-default --config Release`
  - `ctest --test-dir build-default -C Release --output-on-failure`
- [ ] Commit: `build: add focused low-resource target`

## Task 2: Implement hard limits and bounded persistent memory

**Files:**
- Create: `include/edgeai/LowResourceLimits.hpp`
- Create: `include/edgeai/BoundedMemory.hpp`
- Create: `src/BoundedMemory.cpp`
- Create: `tests/test_bounded_memory.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

```cpp
struct LowResourceLimits {
    std::size_t max_rss_bytes = 64u * 1024u * 1024u;
    std::size_t max_model_bytes = 16u * 1024u * 1024u;
    std::size_t max_memory_entries = 64u;
    std::size_t max_memory_bytes = 64u * 1024u;
    unsigned max_threads = 2u;
    std::uint64_t max_startup_ms = 2000u;
};

enum class MemoryAddResult { Added, EvictedOldest, RejectedTooLarge };

class BoundedMemory {
public:
    BoundedMemory(std::string path, std::size_t max_entries, std::size_t max_bytes);
    MemoryAddResult add(const std::string& text);
    std::vector<std::string> search(const std::string& query, std::size_t limit) const;
    std::size_t size() const;
    std::size_t bytes() const;
};
```

- [ ] Write failing tests for default limit values, oversized single-entry rejection, FIFO eviction, deterministic search ordering, bounded reload, and compacted persistence.
- [ ] Run `ctest --test-dir build-low-resource -R bounded_memory --output-on-failure` and confirm the new test fails.
- [ ] Implement byte accounting before allocation/copy where practical.
- [ ] Persist via a temporary sibling file followed by atomic rename; cap data read during reload and discard oldest overflow deterministically.
- [ ] Ensure temporary vectors and token sets are bounded by the query limit and configured byte budget.
- [ ] Run the bounded-memory test plus the existing memory/engine tests.
- [ ] Commit: `feat: add bounded low-resource memory`

## Task 3: Add the low-resource engine and fail-fast CLI

**Files:**
- Create: `include/edgeai/LowResourceEngine.hpp`
- Create: `src/LowResourceEngine.cpp`
- Create: `examples/low_resource.cpp`
- Create: `tests/test_low_resource_engine.cpp`
- Modify: `CMakeLists.txt`

**Interfaces:**

```cpp
struct LowResourceConfig {
    LowResourceLimits limits;
    std::string model_path;
    std::string memory_path;
    unsigned threads = 1u;
};

class LowResourceEngine {
public:
    explicit LowResourceEngine(LowResourceConfig config);
    Response ask(const std::string& prompt);
    const LowResourceLimits& limits() const noexcept;
};
```

CLI contract:

```text
edgeai_low_resource_cli --model PATH [--memory PATH] [--threads 1|2]
                        [--prompt TEXT] [--metrics-json PATH]
```

- [ ] Write failing tests for calculator, deterministic text, memory add/search, neural fallback, explicit unsupported code-search response, missing model, corrupt model, oversized model, and `--threads 3`.
- [ ] Generate a tiny valid transformer fixture in the test setup using existing model serialization; do not commit a second opaque model merely for tests.
- [ ] Validate file existence, regular-file status, byte size, header/version, tensor dimensions, and thread count before constructing the neural backend.
- [ ] Make model-load errors nonzero and diagnostic; never silently fall back to an echo or null backend.
- [ ] Ensure code-search requests return a typed non-neural unsupported response without linking `CodeIndex`.
- [ ] Keep response route/type available so downstream evaluation cannot confuse tool answers with neural answers.
- [ ] Run:
  - `ctest --test-dir build-low-resource -R low_resource_engine --output-on-failure`
  - `build-low-resource/edgeai_low_resource_cli --model build-low-resource/fixtures/tiny.edge --prompt "2+2"`
- [ ] Commit: `feat: add fail-fast low-resource runtime`

## Task 4: Measure real process resources

**Files:**
- Create: `include/edgeai/LowResourceMetrics.hpp`
- Create: `src/LowResourceMetrics.cpp`
- Create: `scripts/measure_low_resource.py`
- Create: `tests/test_measure_low_resource.py`
- Modify: `examples/low_resource.cpp`
- Modify: `CMakeLists.txt`

**Metrics schema:**

```json
{
  "schema": "edgeai.low-resource.metrics.v1",
  "platform": "linux-x86_64",
  "startup_ms": 0,
  "peak_rss_bytes": 0,
  "model_file_bytes": 0,
  "model_weight_bytes": 0,
  "state_payload_bytes": 0,
  "numeric_working_bytes": 0,
  "memory_store_bytes": 0,
  "threads": 1,
  "requests": 0
}
```

- [ ] Write failing parser/gate tests using fixed `/usr/bin/time -v` samples, including locale variation, missing RSS, 65 MiB failure, startup timeout, oversized model, and three-thread failure.
- [ ] Emit internal metrics atomically from the CLI.
- [ ] Implement the Linux harness using `/usr/bin/time -v` as the authoritative peak-RSS source; fail closed if required evidence is missing.
- [ ] Record internal accounting beside OS RSS but never substitute it for OS RSS.
- [ ] Run a mixed canonical workload containing tool, memory, and neural requests and verify all hard budgets.
- [ ] Run normal default tests to prove the profile did not regress the full runtime.
- [ ] Commit: `test: enforce low-resource runtime budgets`

## Task 5: Add the frozen usefulness corpus and separated evaluator

**Files:**
- Create: `data/low_resource_v016/prompts.jsonl`
- Create: `data/low_resource_v016/manifest.json`
- Create: `tools/evaluate_low_resource.py`
- Create: `tests/test_evaluate_low_resource.py`
- Create: `results/v016_low_resource/.gitkeep`

**Corpus contract:**

Each JSONL row contains `id`, `category`, `prompt`, `expected_route`, and either an exact deterministic expectation or an explicit neural rubric. The initial corpus contains at least 40 human-readable prompts: calculator, text tools, memory, unsupported features, and narrow neural tasks. The manifest pins the corpus SHA-256, version, language mix, and counts. Corpus prompts must not be used as training data.

- [ ] Write failing evaluator tests for wrong route, wrong exact answer, empty neural answer, malformed output, timeout, duplicate ID, corpus hash mismatch, and aggregate-score leakage.
- [ ] Implement evaluator output with distinct `tool_accuracy`, `neural_rubric_pass_rate`, `malformed_rate`, latency percentiles, and per-item records.
- [ ] Never publish one blended “accuracy” number.
- [ ] Run the evaluator against the real focused binary and commit the result even if neural quality is poor; label it as a baseline, not success.
- [ ] Manually inspect every neural response in the baseline and record rubric decisions and notes.
- [ ] Commit: `eval: add frozen low-resource usefulness baseline`

## Task 6: Enforce the profile in GitHub Actions

**Files:**
- Create: `.github/workflows/low-resource-ci.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/windows-ci.yml`

- [ ] Add a workflow-validation test or local YAML parse step and first confirm the branch has no low-resource job.
- [ ] On Ubuntu, configure/build the focused target, run focused CTest tests, run the composition test, evaluate the frozen corpus, and enforce RSS/model/thread/startup budgets.
- [ ] On Windows, configure/build and run functional/composition/evaluator tests; publish Windows memory observations separately without treating them as equivalent to Linux `/usr/bin/time`.
- [ ] Upload metrics, evaluator JSON, logs, and the source manifest as artifacts even when a budget gate fails.
- [ ] Add `v0.16-low-resource` to existing CI branch filters without weakening current checks.
- [ ] Pin action major versions and grant only `contents: read`.
- [ ] Run or dispatch the workflow on the branch and retain the run URL and artifact hashes.
- [ ] Commit: `ci: verify low-resource runtime on Linux and Windows`

## Task 7: Publish an evidence-based baseline

**Files:**
- Modify: `README.md`
- Modify: `METAS.md`
- Create: `docs/low-resource-runtime.md`
- Create: `results/v016_low_resource/baseline.json`

- [ ] Document supported hardware, exact build/run commands, offline behavior, exclusions, model format, limits, and error behavior.
- [ ] State separately what is verified: focused build, real process RSS, startup, functional routes, and measured neural baseline.
- [ ] State explicitly that this milestone does not claim parity with large language models.
- [ ] Reproduce the clean build, full tests, focused tests, canonical resource run, and corpus evaluation from a fresh build directory.
- [ ] Compare committed baseline JSON with regenerated output, allowing only documented nondeterministic timing/RSS fields.
- [ ] Review the final diff for accidental model binaries, secrets, generated build output, and unrelated edits.
- [ ] Commit: `docs: publish v0.16 low-resource evidence`

## Final verification

- [ ] `cmake -S . -B build-final-default -DEDGEAI_BUILD_TESTS=ON`
- [ ] `cmake --build build-final-default --config Release`
- [ ] `ctest --test-dir build-final-default -C Release --output-on-failure`
- [ ] `python tests/test_low_resource_composition.py --source . --build build-final-low`
- [ ] `cmake -S . -B build-final-low -DEDGEAI_LOW_RESOURCE=ON -DEDGEAI_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Release`
- [ ] `cmake --build build-final-low --config Release`
- [ ] `ctest --test-dir build-final-low -C Release --output-on-failure`
- [ ] `python tools/evaluate_low_resource.py --binary build-final-low/edgeai_low_resource_cli --corpus data/low_resource_v016/prompts.jsonl --output results/v016_low_resource/reproduced.json`
- [ ] `python scripts/measure_low_resource.py --binary build-final-low/edgeai_low_resource_cli --model build-final-low/fixtures/tiny.edge --workload data/low_resource_v016/prompts.jsonl --output results/v016_low_resource/metrics-reproduced.json`
- [ ] Confirm the GitHub Actions branch run is green and inspect uploaded evidence before claiming completion.
