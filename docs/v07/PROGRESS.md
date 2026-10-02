# Execution ledger — docs/v07/PLAN.md
Baseline: CMake Release built, 10/10 CTest, 57 Python tests passed.
Ruling: keep v0.6 source/checkpoints in independent copy; no shared repository writes.
Ruling: separate learned EOS from max_tokens; legacy models have no EOS.
Tasks 1..6 pending.

Tasks 1..3: implemented, tests red/green; 3 SFT trials completed, weights frozen.
Task 4: main native evaluation and 36 all-logit/24 greedy parity cases passed.
Ruling: add unchanged v0.6 28-prompt audit as supplementary after main test, not
for tuning or checkpoint selection. Main test remains frozen at 194 cases.
Review correction: v0.5 CLI test hardcoded old version; now derives current version
from CMake. Red failure and green full suite recorded.
Review correction: byte-only runtime benchmark correctly rejected EDGEAI7. Energy
probe must run edgeai_generate, not disable that format guard. Red contract saved.
Default model selected by minimum validation NLL (seed22), not highest test score.

Review: split the BPE bounds-check and return into explicit lines/braces to remove GCC misleading-indentation warning; semantics unchanged. Final rebuild/tests cover this edit.

Task 5: complete; instructions and instructions-quick each passed 12/12 stages.
Task 6: complete; Release, portable, Clang ASan+UBSan and fresh extraction/rebuild passed. 11 CTest suites + 69 Python tests per verified build; native demo produced aaeb and EDD with neural=1. Final archive hashes cover delivered files.
