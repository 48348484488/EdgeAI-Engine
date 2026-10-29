#!/usr/bin/env python3
"""Host PTY integration of V19/V20/V21 and V23 main loop.

This tests real getchar, termios and signal handling with deterministic game
helper stubs. It is NOT ARM64/QEMU parity or a complete 2048 reconstruction.
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
ROOT = HERE.parent if HERE.name == 'tests' else HERE


def locate(version, filename):
    candidates = [
        ROOT / 'experiments' / f'2048_{version}' / filename,
        HERE / filename,
        ROOT / filename,
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(f'{version}/{filename}: checked {candidates}')


HARNESS = r'''
#include "candidate_401758.cpp"
#include <cstdio>
#include <cstdint>
#include <string>
using namespace edgeai_2048_v23;
extern "C" void recovered_401704();
extern "C" void recovered_4011cc(unsigned);
static void log(const std::string& s) {
    std::fprintf(stderr, "%s\n", s.c_str());
    std::fflush(stderr);
}
int main() {
    int resets = 0;
    int finishes = 0;
    Hooks h;
    h.startup = [&]{ recovered_401704(); log("START"); };
    h.reset_board = [&](Board& b) {
        b.fill(static_cast<std::uint8_t>(++resets));
        log("RESET:" + std::to_string(resets));
    };
    h.print_score = [&](std::uint32_t s) { log("SCORE:" + std::to_string(s)); };
    h.render_board = [&](Board& b) {
        log("DRAW:" + std::to_string(b[0]) + ":" + std::to_string(b[1]));
    };
    h.render_finish = [&] {
        log("FINISH");
        if (++finishes == 1) log("READY");
    };
    h.read_key = [&] {
        const int key = std::getchar();
        log("KEY:" + std::to_string(key));
        return key;
    };
    for (int i = 0; i < 4; ++i) {
        h.move[i] = [&, i](Board& b, std::uint32_t& s) {
            log("MOVE:" + std::to_string(i));
            b[0] = static_cast<std::uint8_t>(77 + i);
            s += 4u * static_cast<unsigned>(i + 1);
            return 1u;
        };
    }
    h.spawn_tile = [&](Board& b) { b[1] = 55; log("SPAWN"); };
    h.check_first = [&](Board&) { log("CHECK1"); return 1u; };
    h.check_second = [&](Board&) { log("CHECK2"); return 0u; };
    h.on_first_false = [&] { log("FIRST_FALSE"); };
    h.on_second_true = [&] { log("SECOND_TRUE"); };
    h.terminal_mode = [&](unsigned mode) {
        recovered_4011cc(mode);
        log("TERMINAL:" + std::to_string(mode));
    };
    return candidate_401758(h, 100);
}
'''

PREFIX = b'\x1b[H\x1b[J\x1b[?25l\x1b[2J'
RESTORED = b'\x1b[?25h\x1b[m'
CLEANUP = b'\x1b[1;31m' + b' ' * 16 + b'TERMINATED\n' + b'\x1b[0m'


def compile_harness(exe):
    compiler = shutil.which('g++') or shutil.which('clang++')
    if not compiler:
        raise unittest.SkipTest('C++ compiler unavailable')
    source = exe.with_suffix('.cpp')
    source.write_text(HARNESS)
    main = locate('v23', 'candidate_401758.cpp')
    sources = [locate(v, f'candidate_{addr}.cpp') for v, addr in
               [('v19', '401704'), ('v20', '4016ac'), ('v21', '4011cc')]]
    subprocess.run([compiler, '-std=c++17', '-O2', '-Wall', '-Wextra',
                    '-Werror', '-pedantic', '-I', str(main.parent),
                    str(source), *map(str, sources), '-o', str(exe)],
                   check=True, capture_output=True, text=True, timeout=45)


def wait_ready(proc, timeout=5):
    end = time.monotonic() + timeout
    output = b''
    while b'READY\n' not in output:
        remaining = end - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f'No READY from process: {output!r}')
        ready, _, _ = select.select([proc.stderr], [], [], remaining)
        if ready:
            chunk = os.read(proc.stderr.fileno(), 4096)
            if not chunk:
                raise RuntimeError(f'Process exited early ({proc.poll()}): {output!r}')
            output += chunk
    return output


class MainLoopPtyV24(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.temp.name) / '2048-v24'
        compile_harness(cls.exe)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_session(self, keys=b'', interrupt=False):
        master, slave = pty.openpty()
        try:
            before = termios.tcgetattr(slave)
            self.assertEqual(before[3] & 0xa, 0xa)
            proc = subprocess.Popen([str(self.exe)], stdin=slave,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    close_fds=True)
            try:
                initial = wait_ready(proc)
                during = termios.tcgetattr(slave)
                self.assertEqual(during[3], before[3] & ~0xa)
                if interrupt:
                    os.kill(proc.pid, signal.SIGINT)
                else:
                    os.write(master, keys)
                stdout, remaining = proc.communicate(timeout=5)
                self.assertEqual(proc.returncode, 0, (initial + remaining).decode(errors='replace'))
                self.assertEqual(termios.tcgetattr(slave), before)
                return stdout, (initial + remaining).decode().splitlines()
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.communicate(timeout=5)
        finally:
            os.close(slave)
            os.close(master)

    def test_real_keyboard_move_undo_reset_quit(self):
        stdout, events = self.run_session(b'AbRQ')
        self.assertEqual(stdout, PREFIX + RESTORED)
        self.assertEqual(events, [
            'START', 'RESET:1', 'SCORE:0', 'DRAW:1:1', 'FINISH', 'READY',
            'KEY:65', 'MOVE:0', 'SPAWN', 'SCORE:4', 'DRAW:77:55',
            'FINISH', 'CHECK1', 'CHECK2',
            'KEY:98', 'SCORE:4', 'DRAW:1:1', 'FINISH',
            'KEY:82', 'RESET:2', 'SCORE:0', 'SCORE:0',
            'DRAW:2:2', 'FINISH', 'KEY:81', 'TERMINAL:1',
        ])

    def test_ignored_keys_and_second_direction(self):
        stdout, events = self.run_session(bytes([27, ord('a'), ord('B'), ord('q')]))
        self.assertEqual(stdout, PREFIX + RESTORED)
        self.assertEqual(events, [
            'START', 'RESET:1', 'SCORE:0', 'DRAW:1:1', 'FINISH', 'READY',
            'KEY:27', 'KEY:97', 'KEY:66', 'MOVE:1', 'SPAWN',
            'SCORE:8', 'DRAW:78:55', 'FINISH', 'CHECK1', 'CHECK2',
            'KEY:113', 'TERMINAL:1',
        ])

    def test_sigint_during_getchar_restores_terminal(self):
        stdout, events = self.run_session(interrupt=True)
        self.assertEqual(stdout, PREFIX + CLEANUP + RESTORED)
        self.assertEqual(events, ['START', 'RESET:1', 'SCORE:0',
                                  'DRAW:1:1', 'FINISH', 'READY'])


if __name__ == '__main__':
    unittest.main()
