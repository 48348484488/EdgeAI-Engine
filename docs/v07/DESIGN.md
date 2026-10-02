# v0.7 — instruction learning and explicit termination

User goal: a useful CPU-only assistant, small, low energy, fast learning; continue
independently with measurable milestones. This cycle implements the already listed
v0.6 instruction goal. It does not claim frontier-level capability or energy gains.

## Selected design
Reuse the tiny BPE INT8 Transformer and same three v0.6 pretrained checkpoints.
Do not enlarge its hidden dimensions. Extend tokenizer with RESPONSE and EOS after
existing BOS. New EDGEAI7 file layout matches EDGEAI6 except for version/magic and
these two implicit special IDs. Legacy files keep identical semantics. Text never
encodes special IDs; prompt is BOS + user text + RESPONSE; targets are answer + EOS.
The neural CLI and chat use that framing automatically only for EDGEAI7.

Train on synthetic, deterministic, explicitly labeled prompt/answer data. Mask
prompt and padding targets; shift once and train every answer including EOS.
Preserve FP32 master weights / W8A32 export. Test the same expanded model before
and after SFT. No tool calls, hardcoded answers or test data in neural inference.

## Frozen evaluation protocol (before training)
Three seeds 11/22/33, one CPU thread, 60 process-CPU seconds of optimizer work per
seed. Batch 16, AdamW lr 0.001, clipping 1. Validation loss at four checkpoints,
select checkpoint without reading test scores. All seeds reported. Before and
after: greedy native generation, 32 tokens max, exact output and learned EOS
separately. Report combined exact+EOS too; missing EOS is not an exact-termination
success. Restricted expression tasks additionally checked with an AST evaluator.

Tasks: copy, uppercase, small addition, restricted x+k expression. Distinct input
groups across train/validation/test; exclude exact prompts and group overlap.
Diagnostics separate heldout content with familiar templates, unseen templates,
unseen numeric/length ranges, and an entirely untrained reversal task family.
Synthetic template tests are not independent standardized general intelligence
benchmarks. Labels can repeat; inputs/groups must not.

## Safety / compatibility / accounting
Reject invalid specials, truncated files, oversized prompts/targets, no silent
training truncation. Fixed output cap is a safety limit, never reported as EOS.
No dynamic eval/exec or external network needed. Hash data, code and checkpoints;
cache only on verified identity and artifacts. CPU budget excludes initialization,
evaluation and export; report them separately. Joules null unless hardware measured.
Compile baseline, Release, scalar and sanitizers; verify logits and native greedy
output against Python. Portable C++17; Windows unverified unless actually run.
