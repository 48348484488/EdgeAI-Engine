# EdgeAI v0.9 — executable local code lookup and optional reference backend

## Goal and scope
Deliver a useful, evidence-returning source lookup without training, preserve the
0.7.1 models, and provide an explicitly optional local llama-server adapter.
This is based on 0.7.1, not a reconstruction of the missing 0.8 implementation.
User approved the direction and autonomous execution. No outside account changes.

## Design
1. C++17 read-only source snapshot and lexical line search. Relative paths and real
   1-based line numbers, bounded input, deterministic ordering, no shell or model.
   Skip symlinks, hidden paths, generated/dependency folders, binary/invalid UTF-8
   files. Source extensions include C/C++, Python, Pawn and common web languages.
   Return inspection limits and exclusions; no result is not proof of absence.
2. Explicit `buscar codigo:` route with `--code-root`, plus a JSON search CLI.
   Rebuild the bounded snapshot per request so later file edits are not silently
   answered from a stale cache. No automatic write to source or outside paths.
3. Python-standard-library workbench unifies native `.edge` inference and local
   llama-server `/v1/chat/completions`. Loopback only, bounded responses, no proxies,
   redirects or external fallbacks. Transport tests are not model quality tests.
4. A fixed local retrieval fixture, negative cases, raw native outputs and a fair
   comparison harness. Real external-model results remain unavailable unless an
   actual server/model executes. Network download failures are logged, never scored.
5. Existing atomic release packer, all old/new tests, fresh extraction and rebuild.

## Tasks / acceptance
- [x] T1: red tests -> read-only bounded source search; stable snippets and line hits.
- [x] T2: chat route and JSON CLI; absent symbol, ambiguous hits and limits visible.
- [x] T3: loopback reference client + real HTTP contract tests; failures explicit.
- [x] T4: native/optional-reference comparison and retrieval experiment, source hashes.
- [x] T5: full suites, portable build, release zip verification, documented limits.

## Rulings
- No new training this cycle: fix usable evidence and delivery before bigger models.
- Optional external bridge uses Python (no torch); native core remains C++ only.
- C++ lookup is lexical, not semantic understanding, a compiler or a security scanner.
- Network from the runtime failed DNS for GitHub/Hugging Face. Build the adapter,
  test real loopback HTTP, but do not claim real llama-model execution if unavailable.
- Search skips common sensitive names but is NOT a secret detector. Do not use the
  directory as a sandbox against concurrent hostile filesystem mutation.
