# Low-resource runtime

The `EDGEAI_LOW_RESOURCE` profile builds a focused offline executable for inexpensive x86-64 computers without a GPU.

## Components

- deterministic router, calculator, copy, uppercase, reverse, and symbolic-expression tools;
- bounded persistent memory with FIFO eviction;
- one transformer backend using existing mixed/int8/ternary kernels;
- JSON CLI output and atomic metrics output;
- frozen, versioned evaluation corpus.

Code search, Android/JNI, training programs, benchmarks, and alternate model backends are excluded from the focused target.

## Resource contract

The canonical Linux CI run enforces 64 MiB peak RSS, a 16 MiB model-file limit, no more than two threads, and startup within two seconds. `/usr/bin/time -v` is the authoritative RSS source. Internal accounting is retained for diagnosis but cannot replace the OS measurement.

## Fail-fast behavior

The runtime validates the requested thread count and the model's file type, size, header, version, dimensions, and tensors before inference. Missing, non-regular, corrupt, unsupported, or oversized model files terminate with a nonzero exit status. There is no silent null/echo-backend fallback.

Memory entries are bounded by both count and bytes. Oversized individual entries are rejected. When capacity is reached, the oldest entries are evicted and the persistence file is compacted through a temporary sibling file.

## Evidence

`results/v016_low_resource/baseline.json` records the frozen-corpus baseline. Tool accuracy and neural human-review results are separate fields. The current generated fixture passes the deterministic cases but fails human review for neural usefulness.

GitHub Actions uploads Linux metrics/evaluation evidence and Windows functional evidence even when a gate fails. Linux RSS and Windows memory observations are not treated as interchangeable.

## Reproduction

```bash
cmake -S . -B build-low -DCMAKE_BUILD_TYPE=Release \
  -DEDGEAI_LOW_RESOURCE=ON -DEDGEAI_BUILD_TESTS=ON \
  -DEDGEAI_BUILD_BENCHMARK=OFF
cmake --build build-low -j2
ctest --test-dir build-low -R 'edgeai_(bounded_memory|low_resource_engine)' --output-on-failure
./build-low/edgeai_low_resource_fixture build-low/tiny.edge
python3 tools/evaluate_low_resource.py \
  --binary build-low/edgeai_low_resource_cli \
  --model build-low/tiny.edge \
  --corpus data/low_resource_v016/prompts.jsonl \
  --manifest data/low_resource_v016/manifest.json \
  --output evidence/evaluation.json
python3 scripts/measure_low_resource.py \
  --binary build-low/edgeai_low_resource_cli \
  --model build-low/tiny.edge \
  --output evidence/metrics.json
```
