# EdgeAI V32 — independent recovery attestation and orphan cleanup

Date: 2026-10-29.

## Confirmed defect

The V31 watchdog treated a zero exit code and the presence of
`bundle_manifest.json` as sufficient for publication. A synthetic driver
could therefore write an arbitrary JSON manifest and be reported as
`SUCCEEDED`, even though no native library or verified functions existed.

A second defect was in `terminate_group`: it returned immediately when the
direct child exited. Any grandchildren still running in the same process
group were left alive, potentially continuing to write after the watchdog
had reported completion.

## Changes

- Before publication, invoke `edgeai_2048_bundle_verify.py` independently
  with `--elf` and `--rebuild-native`. Require the pinned ELF digest,
  native symbol verification and a byte-identical same-toolchain C++ rebuild.
- Apply the same overall timeout to the second verification process.
- Terminate the entire POSIX process group even if its original leader has
  already exited, including SIGKILL escalation after a short grace period.
- Reject an output destination that appears while verification is running.
- Report `independent_bundle_verification_passed` and
  `native_exports_verified` on a successful recovery.
- Update the old watchdog regression that incorrectly accepted a forged
  manifest and add three new regression tests.

## Actual tests

Command:

```bash
python3 -m unittest discover -s tests -p 'test_edgeai*watchdog*.py' -v
```

Local result: **13/13 passed**, about **11.2 seconds**.

The integration fixture genuinely compiles and links two C++ functions,
produces a native ELF shared library, checks the symbols with `nm -D`,
and rebuilds the library for byte-level attestation. A forged manifest is
rejected. A child process whose parent exits early is killed before it
can create a delayed marker file.

These are infrastructure and synthetic native tests. They are **not**
ARM64 behavioral parity tests, and do not prove 2048 full-game recovery.

## GitHub Actions diagnosis

At the time of this change, the most recent previous EdgeAI CI run was
[#40971782549](https://github.com/48348484488/EdgeAI-Engine/actions/runs/40971782549),
which ended in failure with no executed steps. Its `verify` job returned
`steps: null`; the job-log request returned HTTP 404 BlobNotFound.
This does not establish a source-code hang. The GitHub-side reason remains
unconfirmed.

## Remaining work

Regenerate the 19 source-blind V15 candidates using all 17 translator
modules in one executable environment; integrate the game loop without
callbacks; and compare complete gameplay sessions against the original
AArch64 ELF under QEMU.

**Historical coverage remains 19/23. No additional 2048 function was
recovered or independently validated in V32.**
