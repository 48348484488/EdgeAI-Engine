# EdgeAI Engine

EdgeAI Engine is an experimental, offline, CPU-only inference runtime written in C++17. Its goal is to make useful local automation possible on inexpensive x86-64 computers without a discrete GPU.

The project combines deterministic tools with one compact neural backend. Tool results and neural results are measured separately: a correct calculator answer is not presented as evidence of neural intelligence.

## Current status

The v0.16 low-resource profile is an opt-in runtime for weak PCs.

| Property | Contract |
|---|---:|
| Peak process RSS | at most 64 MiB on the canonical Linux CI workload |
| Model file | at most 16 MiB |
| CPU threads | 1 or 2 |
| Cold startup | at most 2 seconds on the canonical Linux CI runner |
| Network | fully offline |
| Runtime dependencies | C++ runtime only; no Python |

The focused binary includes routing, calculator and text tools, bounded local memory, and a transformer backend. It excludes Android/JNI, code search, training utilities, and unused neural backends.

## Build

Requirements: CMake 3.16+, a C++17 compiler, and Python 3 only for tests/evaluation.

```bash
cmake -S . -B build-low \
  -DCMAKE_BUILD_TYPE=Release \
  -DEDGEAI_LOW_RESOURCE=ON \
  -DEDGEAI_BUILD_TESTS=ON \
  -DEDGEAI_BUILD_BENCHMARK=OFF
cmake --build build-low -j2
ctest --test-dir build-low --output-on-failure
```

Generate an isolated development fixture and run a prompt:

```bash
./build-low/edgeai_low_resource_fixture build-low/tiny.edge
./build-low/edgeai_low_resource_cli \
  --model build-low/tiny.edge \
  --threads 1 \
  --prompt "2+2"
```

The CLI prints structured JSON containing `route`, `neural_used`, and `text`. Missing, corrupt, unsupported, or oversized models fail before backend construction.

## Verified baseline

The frozen v0.16 corpus contains 40 human-readable prompts: 20 deterministic/tool cases and 20 neural cases.

- tool accuracy: **20/20 (100%)** with the generated development fixture;
- neural human-review pass rate: **0/20 (0%)**;
- malformed/empty rate: **0/40**;
- local Windows verification: focused build and focused C++/Python tests passed.

The neural responses from the untrained development fixture were non-empty but not useful. This project does not claim parity with large language models. The baseline exists to prevent tool accuracy from hiding poor neural quality.

Linux GitHub Actions is the authoritative gate for actual peak RSS. Windows results are reported separately.

## Repository layout

```text
include/edgeai/            public C++ interfaces
src/                       runtime implementation
examples/                  runnable CLIs
tests/                     C++ and Python verification
data/low_resource_v016/    frozen evaluation corpus
results/v016_low_resource/ committed baseline evidence
docs/                      design and operational documentation
.github/workflows/         active continuous-integration workflows
```

Historical research documents remain under `docs/history/`. Obsolete experiment workflows and generated trigger/manifest files are not part of the active repository surface.

## Documentation

- [Low-resource runtime](docs/low-resource-runtime.md)
- [v0.16 design](docs/superpowers/specs/2026-10-03-low-resource-runtime-design.md)
- [v0.16 implementation plan](docs/superpowers/plans/2026-10-03-low-resource-runtime.md)
- [Changelog](CHANGELOG.md)
- [Technical goals](METAS.md)

## License and scope

EdgeAI Engine is research software. Results are accepted only when accompanied by reproducible tests or retained evidence. Build success, runtime success, resource compliance, and useful neural quality are separate claims.

