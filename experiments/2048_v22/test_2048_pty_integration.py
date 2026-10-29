#!/usr/bin/env python3
"""V22: integration of V19 startup, V20 SIGINT cleanup and V21 termios on a real PTY.

Host Linux/glibc test only; NOT differential proof against original ARM64/QEMU.
"""
import os
import pty
import select
import shutil
import signal
import subprocess
import tempfile
import termios
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


def build_candidate(executable: Path, sources: list[Path]):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("C++ compiler unavailable")
    harness = executable.with_suffix(".cpp")
    harness.write_text(
        '#include <unistd.h>\n#include <csignal>\n#include <cstring>\n'
        'extern "C" void recovered_401704();\n'
        'extern "C" void recovered_4011cc(unsigned);\n'
        'int main(int argc, char** argv) {\n'
        '  recovered_401704();\n'
        '  if (argc > 1 && std::strcmp(argv[1], "cycle") == 0) {\n'
        '    recovered_4011cc(1); recovered_4011cc(0);\n'
        '  }\n'
        '  if (write(2, "READY\\n", 6) != 6) return 41;\n'
        '  for (;;) pause();\n'
        '}\n'
    )
    subprocess.run(
        [compiler, "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror",
         *map(str, sources), str(harness), "-o", str(executable)],
        check=True, capture_output=True, timeout=40
    )


def wait_for_ready(proc: subprocess.Popen, timeout: float = 5.0) -> bytes:
    deadline = time.monotonic() + timeout
    collected = b""
    while b"READY\n" not in collected:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError(f"child did not become ready: {collected!r}")
        readable, _, _ = select.select([proc.stderr], [], [], left)
        if readable:
            chunk = os.read(proc.stderr.fileno(), 1024)
            if not chunk:
                raise RuntimeError(f"child exited before ready: {proc.poll()} {collected!r}")
            collected += chunk
    return collected


def source_path(version: str, filename: str) -> Path:
    # Repository: experiments/2048_v19 etc; portable ZIP: adjacent source files.
    repo = HERE.parent / f"2048_{version}" / filename
    return repo if repo.is_file() else HERE / filename


class RealPtyLifecycle(unittest.TestCase):
    def check_lifecycle(self, cycle: bool):
        sources = [
            source_path("v19", "candidate_401704.cpp"),
            source_path("v20", "candidate_4016ac.cpp"),
            source_path("v21", "candidate_4011cc.cpp"),
        ]
        for source in sources:
            self.assertTrue(source.is_file(), f"missing source {source}")
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "2048-candidate-lifecycle"
            build_candidate(exe, sources)
            master, slave = pty.openpty()
            try:
                before = termios.tcgetattr(slave)
                self.assertEqual(
                    before[3] & (termios.ECHO | termios.ICANON),
                    termios.ECHO | termios.ICANON
                )
                proc = subprocess.Popen(
                    [str(exe)] + (["cycle"] if cycle else []),
                    stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    close_fds=True
                )
                try:
                    self.assertIn(b"READY\n", wait_for_ready(proc))
                    during = termios.tcgetattr(slave)
                    self.assertEqual(during[3] & 0xA, 0)
                    self.assertEqual(before[:3], during[:3])
                    self.assertEqual(during[3], before[3] & ~0xA)
                    os.kill(proc.pid, signal.SIGINT)
                    stdout, stderr = proc.communicate(timeout=5)
                    self.assertEqual(proc.returncode, 0, stderr)
                    self.assertEqual(stderr, b"")
                    self.assertEqual(termios.tcgetattr(slave), before)
                    prefix = b"\x1b[H\x1b[J\x1b[?25l\x1b[2J"
                    restored = b"\x1b[?25h\x1b[m"
                    cleanup = b"\x1b[1;31m" + b" " * 16 + b"TERMINATED\n" + b"\x1b[0m"
                    self.assertEqual(
                        stdout,
                        prefix + (restored if cycle else b"") + cleanup + restored
                    )
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.communicate(timeout=5)
            finally:
                os.close(slave)
                os.close(master)

    def test_startup_signal_cleanup_restores_real_terminal(self):
        self.check_lifecycle(cycle=False)

    def test_restore_then_raw_again_then_signal(self):
        self.check_lifecycle(cycle=True)


if __name__ == "__main__":
    unittest.main()
