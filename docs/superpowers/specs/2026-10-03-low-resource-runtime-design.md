# EdgeAI v0.16 Low-Resource Runtime Design

**Date:** 2026-10-03  
**Status:** Approved design, pending implementation plan  
**Target branch:** `v0.16-low-resource`

## Purpose

EdgeAI v0.16 will turn the current experimental runtime into an honestly measured CPU-only local AI profile for inexpensive, weak PCs. The project is not claiming general intelligence or parity with large hosted models. It will optimize useful capability per byte of memory, CPU cycle, and model byte while keeping deterministic tools and neural behavior reported separately.

## Target hardware

The reference class is an x86-64 PC with two CPU cores, no discrete GPU, 2–4 GB of system RAM, and Windows or Linux. Runtime use must be fully offline and must not require Python, a network service, or a GPU.

The initial hard budgets are:

- peak process RSS at or below 64 MiB during the reference workload;
- model artifact at or below 16 MiB;
- no more than two worker threads;
- process startup to first completed reference response at or below 2 seconds on the CI reference environment;
- no network access during runtime.

These limits describe the EdgeAI process, not total operating-system memory.

## Scope

The first v0.16 increment will add a low-resource build profile to the existing runtime rather than replace the engine or import a third-party inference runtime.

The profile retains:

- the Router;
- Calculator and deterministic text tools;
- bounded local memory;
- one neural backend selected explicitly for the profile;
- the existing native C++ model format when compatible with the budgets.

The profile excludes by default:

- Android and JNI targets;
- code indexing and repository search;
- training code and Python;
- benchmarks and developer inspection tools not needed by the runtime;
- unused neural backends;
- GPU paths;
- background network services.

Normal builds remain compatible with v0.12 behavior. The low-resource profile is opt-in through CMake.

## Build architecture

CMake will expose `EDGEAI_LOW_RESOURCE`. When enabled, it builds a focused library and a small reference CLI instead of linking every EdgeAI subsystem into one library.

The low-resource library must have an explicit source list containing only the selected router, tools, bounded memory, model loader, kernels, and backend. It must not rely on dead-code elimination as the primary exclusion mechanism.

A generated or compiled configuration exposes the budgets to the runtime. Startup validates the selected model before inference and returns a clear error if its serialized size or declared working-memory requirement exceeds the configured limits.

## Runtime memory design

The initial increment measures current allocations before replacing them. Peak RSS is recorded externally by the verification harness, while the runtime reports model bytes, KV/cache bytes, numeric working memory, and configured thread count.

Unbounded stores are not permitted in the low-resource profile. Local memory has fixed entry and byte limits with deterministic rejection or eviction behavior documented by tests.

After the baseline is reproducible, transient neural buffers will move toward a reusable arena owned by the low-resource runtime. Arena conversion is a subsequent implementation task and must preserve output parity for the selected model.

## Capability measurement

A new frozen evaluation corpus will contain human-readable prompts that are absent from training inputs. Its manifest records file hashes before model evaluation.

Reports must separate:

- deterministic tool cases;
- neural cases;
- correct, incorrect, empty, and malformed outputs;
- latency distribution;
- peak RSS;
- model size;
- thread count.

Tool answers cannot be counted as neural accuracy. A response that merely routes correctly but produces unusable neural text is a neural failure.

The first quality gate does not invent a high accuracy target before a baseline exists. The baseline report becomes the recorded starting point. Subsequent v0.16 changes must not reduce neural correctness or increase malformed neural outputs while claiming an efficiency improvement.

## Verification

Linux CI provides the canonical resource gate because it can measure peak RSS reproducibly. Windows CI verifies build, tests, offline execution, and the same functional corpus, but Windows memory values remain a separate metric rather than being compared directly with Linux RSS.

Required checks are:

1. configure and build with `EDGEAI_LOW_RESOURCE=ON`;
2. prove the focused target does not link excluded subsystems;
3. run deterministic and neural functional tests;
4. run the frozen evaluation corpus;
5. record model size, thread count, startup time, component memory, and peak RSS;
6. fail if a hard budget is exceeded;
7. run the existing normal test suite to prevent regressions.

Reports are committed only when compact and reproducible; larger models and raw artifacts remain CI artifacts.

## Error handling

The reference CLI exits nonzero and prints a specific diagnostic when:

- a model is missing, corrupt, unsupported, or over budget;
- runtime memory accounting detects an overflow;
- the corpus manifest does not match its frozen hashes;
- a network dependency is requested;
- thread configuration exceeds two.

Resource-limit failures are test failures, not warnings.

## Delivery sequence

1. Add failing tests for profile composition and budget enforcement.
2. Add the focused CMake target and reference CLI.
3. Add runtime resource accounting and bounded local memory.
4. Establish and freeze the first useful-prompt corpus.
5. Produce a baseline quality/resource report.
6. Add Linux and Windows CI gates.
7. Optimize allocations and quantization only against the frozen baseline.

## Non-goals for the first increment

- claiming superiority over general-purpose large language models;
- supporting microcontrollers;
- physical-device energy measurements;
- training a new large model;
- adding more deterministic tools solely to inflate the aggregate score;
- hiding neural failures behind router success.

## Success criteria

The first increment is complete when a clean Windows and Linux checkout can build and run the opt-in profile offline, the selected model and process remain inside the stated budgets, the frozen report distinguishes tool and neural capability, and normal EdgeAI builds remain green.
