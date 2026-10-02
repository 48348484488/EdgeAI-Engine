# Registered experiment protocol (written before the runs)

Primary task unchanged from v0.3: six joint (key,value) symbols at the beginning,
random distractors, final query, eight possible target values. Length 32, window 16.
Secondary stress: same generator with length 64; both held-out sets use 1,024 examples.
New test seeds: 268145 for length 32, 268177 for length 64. Training seeds: 11/22/33;
batch generator seed=8100+seed; 400 updates, batch 32, AdamW lr .002, wd .01, clip 1.
Report final fixed-step checkpoints, all runs, no selection of a seed or checkpoint.

Policies: all FP32; all ternary; Q/K FP32 + others ternary; Q/K/V/project FP32 + FFN
ternary; Q/K/V/project INT8 + FFN ternary; all six INT8. Embedding/gates/output FP32.
Matched initial master parameters and exact batch hashes must agree across policies.
The ternary policy also centers each row; INT8 does not. Do not attribute any entire
quality difference exclusively to bit count. INT8 forward uses FP32 activations.

Transformer reference: dim=32, hidden=16 instead of previous 64 to near-match total
parameter count (explicit difference in report). This changes that baseline; do not
mix its results with the v0.3 table. No FLOP matching. All runs use one CPU thread.

Native measurements: repeated model steps; wall and process CPU time; model/file bytes;
RSS by /usr/bin/time when present; no energy estimate from latency or TDP. Same tokens
and architecture across hybrid comparisons. Scalar and automatic kernels tested.

An optional output-head INT8 PTQ evaluation must be separated from the main policies
and use frozen checkpoints without retraining or test-based selection.
