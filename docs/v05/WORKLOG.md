# Ledger — docs/v05/PLAN.md
Base: fonte recuperada da Library, pacote EdgeAI v0.4. Docs de outras revisões
não são autoridade sobre a implementação deste ZIP.
Task 1: complete — CMake Release + CTest: 8/8, log results/v05/baseline_tests.log.
Ruling: atender pedido de autonomia executando todas as etapas locais; nenhum gate
interativo de design. Preservar baseline em commit local e ZIP de origem.
Pre-flight: export Python -> loader C++ usa tags MixedMatrix já existentes;
EDGEAI5 distingue arquitetura, EDGEAI4 continua inalterado.
Task 2: complete — red Python: 8 missing-feature failures; new C++ header missing.
Task 3: complete — 9 CTest suites; 27 reference-logit cases including ring wrap,
odd hidden dimensions and all 3 projection types. Transformer allclose <= 4e-5.
Task 4: active — corpus frozen from the ZIP, 41 files after exclusion, file families
disjoint; training real source/docs, not 8-symbol recall. Research protocol unchanged.
Ruling: test exact-overlap exclusion includes validation as well as train — stronger
separation, but still not proof of no semantic overlap/boilerplate.
Ruling: controller resumes whole completed trials, not partial optimizer steps.
Interrupted current trial restarts; do not claim exact mid-training resume.
Task 6: implementation complete; runner assertions first failed then passed.
Training launch interrupted once by tool timeout; incomplete trial restarted.
Earlier timings of complete trials superseded by the final signature-matched run.

Task 4: complete — 15 fixed-update trials and 6 CPU-budget follow-up trials.
Ruling: fixed-update quality alone favors hybrid but hides cost; add separately
predeclared equal-CPU follow-up, never label it the original preregistered experiment.
Task 5: complete — final trained Python/C++ traces + test metrics, native timings;
RAPL probe has no readable counters. Do not infer energy from elapsed time.
Review: Transformer reported generated-byte count as loops_used; regression fails,
fix to single architecture block (1). Interactive banner still named v0.4; fixed
with failing CLI regression. Neither change alters step math.
Ruling: rerun full research controller after review so distributed artifacts and
status reflect final binaries. Earlier logs are intermediate execution history.
Task 6: final research controller completed all 12 stages; 21 complete research trials.
Task 7: Release/portable/sanitizer suites 9/9, Python 23/23; final clean archive verification follows.
Task 7: complete — extracted candidate rebuilt; 9/9 CTest, 23/23 Python, model inspect and arithmetic smoke passed. Final code/data/model digest identical to compiled candidate.
