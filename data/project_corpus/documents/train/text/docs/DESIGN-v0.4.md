# v0.4 — selective precision experiment

Goal: test the approved hypothesis that preserving Q/K or the whole memory path
at higher precision improves recall while FFN weights remain ternary. Keep the
same equations, dimensions and data across policies; do not add a new architecture.

Approach: add typed FP32 / symmetric per-row INT8 / packed ternary projections to
EDGEAI4, keep EDGEAI2/3 readable, train all policies with the same FP32 master
parameter initialization and data batches, verify every output against native C++.
The native INT8 path is W8A32 (float activations/state), not pure integer inference.
A small additional experiment may quantize the output head, reported separately.

Competing choices: only FP32 would recover a baseline but not test compression;
all ternary repeats a known weak configuration; selective precision directly tests
the hypothesis. No hardware power claim without readable energy counters.

Success: tested export/load, malformed-file rejection, streaming logit parity,
controlled quality/timing/size results including failures, portable source archive.
This is an experimental micro-model, not an advanced assistant or a Claude comparison.
