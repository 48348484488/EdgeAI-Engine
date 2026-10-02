# EdgeAI v0.12 Multi-block Transformer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real multi-block Transformer path to EdgeAI, preserving legacy EDGEAI5/6/7 models and producing a controlled 1-block vs 2-block CPU experiment.

**Architecture:** Replace the single Transformer layer fields with a reusable `TransformerBlock` collection while keeping one shared embedding and output head. Introduce EDGEAI8 only for multi-block exports, give each native block its own KV cache, and reuse the existing v0.7 SFT/evaluation protocol with a configurable block count.

**Tech Stack:** C++17, CMake, Python 3, PyTorch CPU, existing EdgeAI MixedMatrix/ByteBPE tooling.

**Spec:** `docs/superpowers/specs/2026-10-02-transformer-multiblock-v012-design.md`

## Global Constraints

- `block_count` is limited to **1..8**.
- Existing `EDGEAI5`, `EDGEAI6`, and `EDGEAI7` files must continue to load without manual conversion.
- The new multi-block file format is **EDGEAI8**.
- 1-block legacy exports remain allowed to preserve historical parity.
- Each block owns its own KV cache.
- The experiment uses seeds **11, 22, 33**, **1 thread**, and **60 seconds process CPU per architecture per seed**.
- Training/validation/test splits, tokenizer, `dim`, `hidden`, `window`, optimizer, loss, and selection policy must be identical between 1- and 2-block trials.
- Test data must not participate in checkpoint selection.
- No claims about Claude, ChatGPT, general intelligence, or energy savings unless directly measured.

## Review Focus

1. **Legacy model loading:** an unchanged EDGEAI5/6/7 file must become exactly one internal block and preserve old logits within existing tolerance; Task 2 owns this test.
2. **Malformed EDGEAI8 block count:** 0, 9+, truncated matrices, or trailing bytes must reject before unsafe allocation/use; Task 2 owns these tests.
3. **Cache isolation:** block 0 and block 1 must not share keys/values or reset state; Task 3 owns this test.
4. **Python/native parity after autoregressive history:** compare sequences long enough to wrap the attention window for both 1 and 2 blocks; Task 4 owns this test.
5. **Benchmark fairness:** both architectures must prove identical dataset/tokenizer/hyperparameter identity except `blocks`; Task 5 owns this assertion.

---

### Task 1: Python multi-block reference model

**Files:**
- Modify: `tools/transformer_model.py`
- Create: `tests/test_transformer_multiblock.py`

**Interfaces:**
- Consumes: existing `replace_linear()`, `layer_payload_bytes()`, `layer_precision()`.
- Produces: `TransformerBlock(nn.Module)`; `TinyTransformer(..., blocks: int = 1)`; `TinyTransformer.export_config()` including `blocks`.

- [ ] **Step 1: Write the failing Python tests**

Add tests:
- `test_two_blocks_have_independent_parameters`
- `test_block_count_rejects_zero_and_nine`
- `test_one_block_forward_matches_legacy_equations`
- `test_numeric_weight_bytes_counts_all_blocks`

Assertions pin `blocks=2`, independent parameter objects, valid output shape, and rejection outside 1..8.

- [ ] **Step 2: Run the tests and observe RED**

Run: `python -m unittest tests.test_transformer_multiblock -v`

Expected: FAIL because `TinyTransformer` has no `blocks` argument / block collection yet.

- [ ] **Step 3: Implement the Python block abstraction**

In `tools/transformer_model.py`:
- define `class TransformerBlock(nn.Module)`;
- change signature to `TinyTransformer(dim=64, hidden=96, window=64, precision='int8', rope_base=10000., vocab_size=256, blocks=1)`;
- store blocks in `nn.ModuleList`;
- apply each block sequentially;
- keep `emb` and `out` shared;
- include `blocks` in `export_config()`;
- update `numeric_weight_bytes(model)` to count every block plus the shared output head.

- [ ] **Step 4: Run focused tests GREEN**

Run: `python -m unittest tests.test_transformer_multiblock -v`

Expected: all tests PASS.

- [ ] **Step 5: Run existing Python transformer/SFT tests**

Run: `python -m unittest discover -s tests -p 'test_*.py'`

Expected: no regressions.

- [ ] **Step 6: Commit**

Commit message: `feat: add Python multi-block Transformer reference`

---

### Task 2: Native model structure and EDGEAI8 serialization

**Files:**
- Modify: `include/edgeai/TransformerModel.hpp`
- Modify: `src/TransformerModel.cpp`
- Modify: `tests/test_transformer.cpp`
- Modify: `tests/test_instruction.cpp`

**Interfaces:**
- Consumes: `MixedMatrix`, `ByteBPE`, existing legacy serialization.
- Produces: `struct TransformerBlock { MixedMatrix query,key,value,project,up,down; };`; `TransformerConfig::blocks`; `TransformerModel::blocks`; shared `TransformerModel::output`.

- [ ] **Step 1: Write failing C++ round-trip and compatibility tests**

Extend `tests/test_transformer.cpp` to require:
- `make_transformer_demo(..., 2)` produces two independent blocks;
- save/load of a 2-block model begins with `EDGEAI8`;
- round-trip preserves block count, parameter count, weight bytes, and tensors;
- block counts 0 and 9 reject;
- truncated EDGEAI8 and trailing bytes reject;
- `state_payload_bytes()` doubles its KV state contribution from 1 to 2 blocks.

Keep legacy 1-block round-trip tests.

- [ ] **Step 2: Run C++ test RED**

Run:
`cmake -S . -B build-v012 -DCMAKE_BUILD_TYPE=Release && cmake --build build-v012 -j2 --target edgeai_test_transformer edgeai_test_instruction && ctest --test-dir build-v012 -R 'edgeai_(transformer|instruction)' --output-on-failure`

Expected: FAIL/compile failure because multi-block structures/signatures do not exist.

- [ ] **Step 3: Implement `TransformerBlock` and config**

In `include/edgeai/TransformerModel.hpp`:
- add `std::uint32_t blocks=1` to `TransformerConfig`;
- add `TransformerBlock`;
- replace six per-model block matrices with `std::vector<TransformerBlock> blocks_data` (or an equally explicit non-conflicting name);
- keep `MixedMatrix output`;
- extend `make_transformer_demo(dim, hidden, window, blocks=1)`.

- [ ] **Step 4: Implement EDGEAI8 writer/reader and legacy adapter**

In `src/TransformerModel.cpp`:
- validate 1..8 blocks;
- write EDGEAI8 layout from the spec for multi-block models;
- load EDGEAI8 tokenizer mode, merges, embedding, N blocks, shared output;
- load EDGEAI5/6/7 into a one-element block vector;
- reject invalid counts, inconsistent shapes, truncation, and trailing payload;
- update `valid()`, `weight_bytes()`, `parameter_count()`, and `state_payload_bytes()`.

- [ ] **Step 5: Run focused C++ tests GREEN**

Run: `ctest --test-dir build-v012 -R 'edgeai_(transformer|instruction)' --output-on-failure`

Expected: 2/2 PASS.

- [ ] **Step 6: Commit**

Commit message: `feat: add EDGEAI8 multi-block model format`

---

### Task 3: Multi-block C++ inference and independent KV caches

**Files:**
- Modify: `include/edgeai/TransformerBackend.hpp`
- Modify: `src/TransformerBackend.cpp`
- Modify: `tests/test_transformer.cpp`

**Interfaces:**
- Consumes: `TransformerModel::blocks_data` from Task 2.
- Produces: per-block runtime state; unchanged public `step(uint32_t)`, `reset()`, `infer()`, `greedy_token()`; accurate `numeric_working_bytes()`.

- [ ] **Step 1: Add failing runtime tests**

Add tests requiring:
- 2-block `step()` returns finite logits;
- cache usage remains bounded by `window` for every block;
- running more than `window` tokens exercises wraparound;
- `reset()` restores deterministic first-token logits;
- changing only block 1 weights changes final logits, proving block 1 is executed;
- reported working bytes increase for 2 blocks.

- [ ] **Step 2: Run focused test RED**

Run: `cmake --build build-v012 -j2 --target edgeai_test_transformer && ctest --test-dir build-v012 -R edgeai_transformer --output-on-failure`

Expected: FAIL because backend still assumes one set of Q/K/V/cache buffers.

- [ ] **Step 3: Implement per-block runtime state**

Create a private runtime state type in `TransformerBackend` containing Q/K/V, attention scratch, MLP scratch, KV cache, scores, `next`, and `used` for one block. Iterate blocks sequentially for each token while sharing token position/RoPE frequency and final logits.

- [ ] **Step 4: Make reset/accounting cover all blocks**

`reset()` clears every block cache/index. `numeric_working_bytes()` sums all block runtime buffers plus shared embedding/logits/workspace.

- [ ] **Step 5: Run focused and full C++ suite**

Run:
`ctest --test-dir build-v012 --output-on-failure`

Expected: all CTest targets PASS.

- [ ] **Step 6: Commit**

Commit message: `feat: run multi-block Transformer in native backend`

---

### Task 4: Python export and Python/C++ parity for EDGEAI8

**Files:**
- Modify: `tools/transformer_model.py`
- Modify: `tools/verify_instructions.py`
- Modify: `tests/test_transformer_multiblock.py`
- Create: `tools/verify_multiblock.py`

**Interfaces:**
- Consumes: Python `TinyTransformer(blocks=N)`, native EDGEAI8 loader/backend.
- Produces: `export_transformer()` capable of EDGEAI8; parity report JSON with `all_passed`, cases, max error, tolerances, block count.

- [ ] **Step 1: Add failing export tests**

Require:
- `blocks=2` exports magic `EDGEAI8\0`;
- `blocks=1` with instruction tokenizer can still export legacy EDGEAI7;
- invalid block precision/shape is rejected.

- [ ] **Step 2: Run export tests RED**

Run: `python -m unittest tests.test_transformer_multiblock -v`

Expected: multi-block export FAIL because exporter knows only the seven single-block matrix names.

- [ ] **Step 3: Implement multi-block export**

Update `export_transformer(model, path, max_generate=128, tokenizer=None)`:
- emit EDGEAI8 when `model.blocks > 1`;
- encode tokenizer mode exactly as spec;
- serialize six matrices per block then shared output;
- retain existing legacy path for one block.

- [ ] **Step 4: Add parity verifier**

`tools/verify_multiblock.py` must create/load deterministic 1- and 2-block fixtures and compare Python logits with `edgeai_token_logits` for:
- scalar and auto kernels;
- normal sequence;
- a sequence longer than the attention window to force cache wraparound.

Use existing tolerance `atol=6e-5, rtol=6e-5`.

- [ ] **Step 5: Run parity GREEN**

Run: `python tools/verify_multiblock.py --build build-v012 --out results/v012/multiblock_parity.json`

Expected: `all_passed=true` for 1 and 2 blocks.

- [ ] **Step 6: Commit**

Commit message: `test: verify EDGEAI8 Python native parity`

---

### Task 5: Controlled 1-block vs 2-block SFT experiment

**Files:**
- Create: `benchmarks/instruction_blocks_v012.py`
- Create: `benchmarks/instruction_blocks_eval_v012.py`
- Create: `tests/test_v012_experiment.py`
- Generate: `results/v012/training.json`
- Generate: `results/v012/evaluation.json`

**Interfaces:**
- Consumes: frozen `data/instructions_v07`, v0.6 base checkpoints, `expand_checkpoint()`, multi-block model/export.
- Produces: paired experiment reports where architecture identity differs only by `blocks in {1,2}`.

- [ ] **Step 1: Write experiment-contract tests**

Tests assert:
- seeds exactly `[11,22,33]`;
- threads exactly `1`;
- default CPU budget exactly `60.0`;
- architectures exactly `[1,2]`;
- identity includes dataset hash, tokenizer/config, optimizer settings and block count;
- comparison rejects reports where any controlled hyperparameter differs besides block count.

- [ ] **Step 2: Run tests RED**

Run: `python -m unittest tests.test_v012_experiment -v`

Expected: FAIL because v0.12 experiment module does not exist.

- [ ] **Step 3: Implement paired trainer**

Adapt the existing `instruction_v07.py` protocol rather than inventing new data/selection rules. For each seed and block count:
- initialize deterministically from the same compatible pretrained base;
- for block 2, initialize the added second block deterministically from the seed without mutating block 1 copied weights;
- train for process CPU budget;
- select by validation response NLL at 25/50/75/100% CPU checkpoints;
- save model/checkpoint and hashes.

The report records parameters, steps, CPU time, validation NLL, file bytes and calculated model/cache bytes.

- [ ] **Step 4: Implement native evaluation**

Evaluate every selected model through native `edgeai_generate` on the same four existing test splits and report total/per-family exact/correct/EOS metrics plus timing.

- [ ] **Step 5: Run the full 6-trial experiment**

Run:
`python benchmarks/instruction_blocks_v012.py --cpu-seconds 60 --seeds 11 22 33 --threads 1 --out results/v012/training.json --model-dir models/v012`

Then:
`python benchmarks/instruction_blocks_eval_v012.py --build build-v012 --report results/v012/training.json --out results/v012/evaluation.json`

Expected: 6 completed training trials and 6 selected native evaluations.

- [ ] **Step 6: Commit code and reproducible reports**

Commit message: `bench: compare one and two Transformer blocks`

---

### Task 6: Full verification, documentation, and release decision

**Files:**
- Modify: `CMakeLists.txt`
- Modify: `BENCHMARK_RESULTS.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Generate: `results/v012/verification.json`

**Interfaces:**
- Consumes: Tasks 1–5 and their reports.
- Produces: version 0.12 metadata and a human-readable decision that does not hide quality/cost trade-offs.

- [ ] **Step 1: Set project version to 0.12.0**

Update CMake project version only after implementation and experiment reports exist.

- [ ] **Step 2: Run complete Python suite**

Run: `python -m unittest discover -s tests -p 'test_*.py'`

Expected: 0 failures.

- [ ] **Step 3: Run complete Release C++ suite**

Run:
`cmake -S . -B build-v012-final -DCMAKE_BUILD_TYPE=Release && cmake --build build-v012-final -j2 && ctest --test-dir build-v012-final --output-on-failure`

Expected: 0 failures.

- [ ] **Step 4: Run portable no-SIMD suite**

Run:
`cmake -S . -B build-v012-nosimd -DCMAKE_BUILD_TYPE=Release -DEDGEAI_DISABLE_SIMD=ON && cmake --build build-v012-nosimd -j2 && ctest --test-dir build-v012-nosimd --output-on-failure`

Expected: 0 failures.

- [ ] **Step 5: Run ASan+UBSan suite**

Run:
`cmake -S . -B build-v012-san -DCMAKE_BUILD_TYPE=Debug -DEDGEAI_SANITIZERS=ON && cmake --build build-v012-san -j2 && ctest --test-dir build-v012-san --output-on-failure`

Expected: 0 failures.

- [ ] **Step 6: Re-run multi-block parity on final build**

Run: `python tools/verify_multiblock.py --build build-v012-final --out results/v012/multiblock_parity-final.json`

Expected: `all_passed=true`.

- [ ] **Step 7: Verify legacy artifacts**

Hash the 142 pre-v0.12 `.edge/.pt` files that are not newly created under `models/v012` and confirm the implementation work did not silently rewrite them.

- [ ] **Step 8: Write measured results**

Update `BENCHMARK_RESULTS.md` with:
- per-seed and aggregate quality;
- parameter/file/cache/working-memory costs;
- native latency measurements;
- RSS when available;
- energy as `null` if no real sensor;
- explicit decision whether 1 or 2 blocks remains the default.

Update README's short data table and “next experiment” section using only verified numbers.

- [ ] **Step 9: Create verification manifest**

`results/v012/verification.json` records final commit-relevant hashes, commands, test counts, parity result, experiment report hashes, and legacy-artifact preservation result.

- [ ] **Step 10: Final commit**

Commit message: `release: document EdgeAI v0.12 multi-block experiment`
