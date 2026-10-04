# Technical goals

## Product direction

Build a useful, fully offline local AI system for inexpensive CPU-only computers. Improve capability per byte, CPU cycle, and watt before increasing model size.

## v0.16 acceptance criteria

- focused x86-64 runtime with no GPU or Python dependency;
- at most 64 MiB peak RSS in the canonical Linux CI workload;
- model file no larger than 16 MiB;
- one or two CPU threads;
- deterministic tools and neural output evaluated separately;
- bounded memory and fail-fast model validation;
- reproducible Linux and Windows CI evidence.

## Quality policy

A compiled binary is not proof of a useful AI. A tool-correct result is not neural accuracy. Neural progress requires a frozen corpus, human-readable outputs, retained per-item evidence, and explicit human review.

The current v0.16 development fixture establishes infrastructure and a baseline. It does not yet produce useful neural answers and does not claim parity with large language models.

## Next research milestones

1. Train a compact model on an auditable corpus that excludes evaluation prompts.
2. Improve the neural human-review pass rate without exceeding the v0.16 budgets.
3. Reproduce the Linux budget on a physical low-cost dual-core x86-64 PC.
4. Reduce the 64 MiB process target toward 32 MiB after quality is measurable.

