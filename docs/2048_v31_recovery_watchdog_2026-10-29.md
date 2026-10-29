# EdgeAI V31 — bounded recovery watchdog and V15 dependency readiness

Date: 2026-10-29.

## Actual changes

Added tools/edgeai_v15_watchdog.py and tests/test_edgeai_v15_watchdog.py.
The watchdog checks the original ELF SHA-256, recursively parses Python
imports used by the V15 translator/recovery driver, checks native tools,
and launches the existing V27 atomic recovery in an isolated temporary
directory. It emits heartbeat records, applies a hard deadline, terminates
the child process group on timeout, and only publishes the completed
bundle by a same-filesystem rename. It preserves a pre-existing destination
and can write a machine-readable report.

The watchdog is not a new lifter and does not increase recovered-function
coverage. It distinguishes a genuine child timeout from failure before
a GitHub Actions runner starts.

## Tests performed locally

Command: python3 -m unittest discover -s tests -p 'test_edgeai_v15_watchdog.py' -v

Result: **10/10 passed** in **3.15 s**, including a synthetic sleeping child
terminated by the watchdog, a failing child, missing transitive imports,
wrong ELF hash, atomic success and failure, and destination protection.

The pinned 2048 ELF was independently extracted from the V21 local package.
Its SHA-256 was confirmed as:

a3ca49d16ca6428291574ebd3f7c54153ef0913f8aa1eee4279408c3bf9d499b

Using the connected private repository's current main tree and fetching
each source file, a recursive local-import audit found **17 V15 Python
modules, 0 missing, 0 fetch errors**. This verifies source-file presence,
not successful execution of the full translator. The local V30 ZIP contains
only a partial tool subset; it cannot run the complete V15 regeneration.

## GitHub Actions status

GitHub Actions run #40967143153 (EdgeAI CI) completed with failure in
approximately four seconds; the only job verify had steps: null.
Fetching the job logs returned 404 BlobNotFound. This is evidence of a
pre-step execution failure, **not** a code hang. Its exact GitHub-side
cause remains unconfirmed.

## Reproduction with a complete repository checkout

Preflight without regeneration:

    python3 tools/edgeai_v15_watchdog.py /path/to/2048.elf \
      --preflight-only --report /tmp/edgeai-v15-preflight.json

Regenerate under a hard deadline (requires the full source tree):

    python3 tools/edgeai_v15_watchdog.py /path/to/2048.elf \
      --destination /tmp/edgeai-v15-recovered \
      --timeout 180 --heartbeat 5 --report /tmp/edgeai-v15-run.json

## Remaining limits

**The real 19-function V15 regeneration was not executed in this run.**
The recovered count remains historically **19/23**, and the main loop,
terminal/startup integration and full-game QEMU comparison are pending.
The new watchdog's 10 tests use synthetic drivers and do not establish
ARM64 behavioral parity.
