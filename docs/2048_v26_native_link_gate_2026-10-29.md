# EdgeAI V26 — native C++ export and strict-link gate (2026-10-29)

Added `tools/edgeai_cpp_link_gate.py` and `tests/test_edgeai_cpp_link_gate.py` to replace source-text-only assumptions with **real host compiler and ELF symbol evidence**. Each `candidate_<addr>.cpp` is compiled using `g++ -std=c++17 -fPIC -c`, and `nm -g --defined-only` must show an unmangled, globally defined text symbol `recovered_<addr>`. With `--strict-link`, all supplied objects must link as a shared library using `-Wl,-z,defs`, rejecting unresolved references.

**Local results:** 12/12 new tests passed. The V19–V21 startup/terminal/cleanup candidates at `0x401704`, `0x4011cc` and `0x4016ac` produced 3/3 valid native exports and linked together successfully with strict undefined-symbol checks. Adding the V23/V24 main candidate `candidate_401758.cpp` gave 3/4 exports: it compiles, but defines a semantic callback wrapper `edgeai_2048_v23::candidate_401758`, **not** a native `recovered_401758` export. The new gate correctly rejects that four-file bundle (exit 2) and skips linking.

Tests cover genuine exports, declarations without bodies, misleading comments and strings, C++ name mangling, data symbols, syntax errors, unresolved external references, multiple-file linkage, duplicate addresses, empty directories and CLI reporting.

**Stall check:** Local tests completed normally. GitHub Actions private run [#40924004890](https://github.com/48348484488/EdgeAI-Engine/actions/runs/40924004890) has a completed failed `verify` job with **zero steps**, so it does not establish a code hang and the runner failure is not diagnosed.

**Limits:** The native Linux check is not ARM64 ABI validation, QEMU comparison, or whole-game reconstruction. No new original ARM64 function was behaviorally verified: coverage remains **19/23**. Strict linking of three candidates does not imply dependency closure of the main game. Next: persist/regenerate the 19 V15 C++ providers, replace callback-only main with a native export, and perform full-session differential validation against the original ELF under QEMU.

Reproduction:

```bash
python3 -m unittest discover -s tests -p 'test_edgeai_cpp_link_gate.py' -v
python3 tools/edgeai_cpp_link_gate.py --generated-dir /path/to/v19-v21-candidates --strict-link --output /tmp/v26.json
```
