# Task 3 report: deterministic Portuguese response-only training

**Status: DONE_WITH_CONCERNS.** The implementation and all torch-independent contracts are reviewable and committed. The mandatory two real quick-training runs remain unverified because the only installed Python runtime cannot load the existing PyTorch native DLL.

## Audit and implementation

The partial `benchmarks/portuguese_v017.py` was 21,611 bytes of zero bytes; it had no recoverable source. The test file was intact. The trainer was reconstructed against the Task 3 brief, the sealed Task 1 dataset accessors, `ByteBPE`, `sft_model.response_loss`, and `TinyTransformer`.

The implementation provides quick/release `TrainConfig` profiles, response-only prompt masking with EOS supervision, sealed train-ID-only tokenizer inputs, replayable shuffled batches, exact response-token budgets, finite loss checks, validation-only selection, resume identity/progress validation, deterministic CPU training, checkpoints, and a `training.json` report with timings, token counts, curves, dependency versions, and hashes. Output paths do not affect checkpoint identity or deterministic checkpoint fields. The trainer does not emit `selected.edge`; Task 4 owns EDGEAI8 export.

## RED/GREEN evidence

- The supplied handoff recorded seven torch-independent contracts as green before the interrupted implementation. The original trainer source was zeroed by the time this recovery started, so the first fresh suite import failed on a null byte rather than reproducing that earlier state.
- Added an output-path identity regression test. It failed first because `out` was part of resume identity, then passed after output location was excluded from semantic configuration and checkpoint metadata.
- Extended tokenizer leakage coverage with a held-out test row. It failed first because a test row could affect merges, then passed after tokenizer input was restricted to IDs in the sealed train partition.
- Final torch-independent run: **58 tests passed** across the trainer contracts, Task 1 dataset tests, and Task 2 evaluator tests.
- `python -m py_compile benchmarks/portuguese_v017.py tests/test_portuguese_training_v017.py`: passed.
- Full `python -m unittest tests.test_portuguese_training_v017 -v`: ten tests passed; the real CPU-training test errored when importing PyTorch, as detailed below. The integration test still requires actual training and was not mocked or weakened.

## Real-training blocker and quick-run results

`where.exe python` found the Python 3.12 installation and a Windows Store execution alias. `py -0p` listed only `C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe`. Importing Torch with that interpreter reaches `torch\\__init__.py` and fails in `_load_dll_libraries()` with:

```text
OSError: [WinError 1114] Uma rotina de inicialização da biblioteca de vínculo dinâmico (DLL) falhou.
Error loading "C:\Users\Admin\AppData\Local\Programs\Python\Python312\Lib\site-packages\torch\lib\c10.dll" or one of its dependencies.
```

The Windows Store alias reports that Python was not found. No package installation was attempted. The trainer converts this import failure into a clear `RuntimeError: PyTorch runtime unavailable: OSError: [WinError 1114] ... c10.dll or one of its dependencies.` before it creates checkpoints or reports.

Both clean-directory attempts failed with exit code 1 and the same PyTorch error:

```text
python benchmarks/portuguese_v017.py --profile quick --threads 1 --out build/task3-quick-a
python benchmarks/portuguese_v017.py --profile quick --threads 1 --out build/task3-quick-b
```

Both output paths were absent before invocation and remained absent afterward. No checkpoint, `training.json`, fabricated loss, or model result was produced. Consequently finite real-training losses, deterministic checkpoint hashes, and the required pair of successful quick runs remain unverified. Re-run those two quick profiles when a working Torch runtime is available.

## Task 3 fix round 1/5

Status remains **DONE_WITH_CONCERNS**. Findings 1–4 are addressed and committed; finding 5 is still blocked by the unchanged real PyTorch runtime error above.

### RED/GREEN evidence

1. **No test split file reads:** `python -m unittest tests.test_portuguese_training_v017.TrainingContracts.test_training_loader_and_tokenizer_never_open_test_jsonl -v` first failed with `AssertionError: trainer opened sealed test.jsonl` from the old full `load_dataset` path. It passed after adding verified train/valid-only reads, manifest and source-provenance checks, and exact generated-content comparison. The regression holds a `Path.open` guard across both dataset loading and tokenizer construction. The Task 1 dataset module remains unchanged so its generator hash contract stays valid.
2. **Resume schema matches emitted checkpoints:** `python -m unittest tests.test_portuguese_training_v017.TrainingContracts.test_resume_validates_emitted_checkpoint_progress_shape -v` first errored because validation required a fabricated `best_checkpoint` key absent from emitted checkpoints. The fixture now follows the trainer's emitted top-level metadata names (`protocol`, `identity`, `versions`, `config`, `seed`, `step`, token counts, curves, batch digest, and selected validation fields); it passed after validation was aligned to those fields.
3. **Resume bounds and curve progression:** `python -m unittest tests.test_portuguese_training_v017.TrainingContracts.test_resume_rejects_impossible_steps_budgets_and_curve_progression -v` first failed because the validator accepted three impossible payloads: step 3 when the configured maximum was 2; seven response tokens for a step budget of eight; and a validation curve missing step 1. It passed after enforcing the configured step ceiling, exact per-step token totals, sequential loss and validation curves, and selected-metric consistency.
4. **Aggregate artifact paths resolve:** `python -m unittest tests.test_portuguese_training_v017.TrainingContracts.test_aggregate_report_artifact_keys_resolve_to_checkpoint_files -v` first errored because `write_training_report` did not exist and the old aggregate keys prefixed nonexistent `seed-11/` directories. It passed after report generation began recording each real relative filename and checking that the file exists with the reported hash.

### Verification after fixes

- `python -m unittest tests.test_portuguese_training_v017.TrainingContracts tests.test_portuguese_data_v017 tests.test_evaluate_portuguese_v017 -v`: **61 passed**.
- `python -m unittest tests.test_portuguese_training_v017 -v`: all 13 torch-independent trainer contracts passed; the one real CPU-training test errored on the existing `WinError 1114` loading `torch\\lib\\c10.dll`. The real test remains intact.
- `python -m py_compile benchmarks/portuguese_v017.py tools/portuguese_data_v017.py tests/test_portuguese_training_v017.py`: passed.
- Repeated the two quick commands in previously absent `build/task3-round1-a` and `build/task3-round1-b` directories. Both exited 1 at PyTorch import with the same `c10.dll` error; both directories remained absent, so no training artifacts were created.
- No package installation or mocked/fabricated training was used. Finding 5 and the two successful real quick runs remain unverified.

## Task 3 fix round 2/5

Status remains **DONE_WITH_CONCERNS** pending a successful hosted Actions run; local Windows Torch remains unavailable. Added a narrowly scoped hosted smoke workflow and a stdlib-only verifier so the required real quick profiles can run on Ubuntu without weakening or mocking the local integration test.

### RED/GREEN evidence

- **RED:** Before adding the verifier/workflow, `python -m unittest tests.test_portuguese_v017_training_workflow -v` failed importing `tools.verify_portuguese_training_runs` (`ModuleNotFoundError`), establishing the missing behavior boundary.
- **GREEN:** After implementation, that workflow-contract module passed **2 tests**. Its tests assert the branch-only push trigger plus manual dispatch, read-only contents permission, Ubuntu runner, CPU PyTorch wheel index and pinned `torch==2.10.0`, matching `numpy>=1.26,<3`, contract-suite invocation, two distinct quick output directories, explicit checks of both exit codes, unconditional artifact upload, and absence of `selected.edge`. The verifier fixture confirms timing-only differences are ignored, deterministic report drift fails, and tampered checkpoint bytes fail hash verification.
- `python -m unittest tests.test_portuguese_training_v017.TrainingContracts tests.test_portuguese_data_v017 tests.test_evaluate_portuguese_v017 tests.test_portuguese_v017_training_workflow -v`: **63 passed**.
- `python -m py_compile tools/verify_portuguese_training_runs.py tests/test_portuguese_v017_training_workflow.py`: passed.
- Parsed the workflow with the installed PyYAML `BaseLoader` and inspected the folded unittest command; the workflow has `name`, `on`, `permissions`, and `jobs` top-level mappings, and the command resolves to the expected single-line `python -m unittest ... -v` invocation. `git diff --check`: passed.

### Hosted run and remaining blocker

The new `.github/workflows/portuguese-v017-training-smoke.yml` triggers on pushes only to `v0.17-portuguese-neural` and on `workflow_dispatch`; it requests only `contents: read`. It installs the same CPU Torch pin and NumPy range as existing CI, executes data/training/evaluator contracts, creates two clean evidence directories, and invokes the actual quick trainer twice with `--threads 1`. Both commands run even if the first exits unsuccessfully; the job fails if either exit code is nonzero. The stdlib verifier compares every report field except the explicit top-level timing object, checks tokenizer fingerprints against each run, and recomputes every reported artifact hash in both directories. An `if: always()` upload step retains run logs, any reports/checkpoints emitted, and the two exit statuses, including when training or comparison fails.

Re-ran the unmocked local integration test `python -m unittest tests.test_portuguese_training_v017.RealCPUTraining.test_finite_losses_exact_budget_and_identical_artifact_hashes -v`. It still errors before producing artifacts: Python 3.12 fails importing the existing Torch installation with `OSError: [WinError 1114] ... Error loading "C:\Users\Admin\AppData\Local\Programs\Python\Python312\Lib\site-packages\torch\lib\c10.dll" or one of its dependencies`; the trainer raises `RuntimeError: PyTorch runtime unavailable: OSError: [WinError 1114] ...`. No package installation, fake success, checkpoint, or selected.edge was created. The controller must publish/run the workflow and inspect its uploaded evidence; until then, the mandatory two successful real quick runs and deterministic checkpoint hashes remain unverified.
