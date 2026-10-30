"""Offline regression tests for bounded V15 recovery execution."""
import hashlib
from pathlib import Path
import sys
import tempfile
import textwrap
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from edgeai_v15_watchdog import preflight, run, write_report


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.elf = self.root / 'game.elf'
        self.elf.write_bytes(b'test arm64 fixture')
        self.sha = hashlib.sha256(self.elf.read_bytes()).hexdigest()
        self.tools = self.root / 'tools'
        self.tools.mkdir()
        for name in ('aarch64_multistage_batch.py', 'edgeai_2048_v15_recovery.py',
                     'edgeai_2048_bundle_verify.py', 'edgeai_cpp_link_gate.py'):
            (self.tools / name).write_text('# synthetic test tool\n')
        self.dest = self.root / 'published'

    def driver(self, script):
        (self.tools / 'edgeai_2048_v15_recovery.py').write_text(textwrap.dedent(script))

    def test_recursive_dependency_preflight(self):
        (self.tools / 'aarch64_multistage_batch.py').write_text('from aarch64_leaf_lifter import lift\n')
        (self.tools / 'aarch64_leaf_lifter.py').write_text('import aarch64_scalar_lifter\n')
        (self.tools / 'aarch64_scalar_lifter.py').write_text('')
        proof = preflight(self.elf, self.tools, self.sha)
        self.assertEqual(proof['module_count'], 6)

    def test_missing_transitive_dependency_blocks(self):
        (self.tools / 'aarch64_multistage_batch.py').write_text('import aarch64_missing\n')
        with self.assertRaisesRegex(ValueError, 'aarch64_missing.py'):
            preflight(self.elf, self.tools, self.sha)

    def test_wrong_elf_hash_blocks(self):
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            preflight(self.elf, self.tools, '0'*64)

    def test_preflight_does_not_execute_driver(self):
        self.driver('raise RuntimeError("must not execute")\n')
        result = run(self.elf, self.dest, self.tools, expected_sha256=self.sha,
                     preflight_only=True)
        self.assertEqual(result['status'], 'PREFLIGHT_PASSED')
        self.assertFalse(self.dest.exists())

    def test_forged_manifest_is_not_published(self):
        self.driver('''
            import pathlib, sys
            dest = pathlib.Path(sys.argv[sys.argv.index('--destination')+1])
            dest.mkdir()
            (dest/'bundle_manifest.json').write_text('{"test":true}')
        ''')
        result = run(self.elf, self.dest, self.tools, expected_sha256=self.sha,
                     timeout=5, heartbeat=.01)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(self.dest.exists())
        self.assertIn('independent verifier', result['stderr_tail'])

    def test_failed_child_does_not_publish(self):
        self.driver('import sys; print("bad child", file=sys.stderr); sys.exit(9)\n')
        result = run(self.elf, self.dest, self.tools, expected_sha256=self.sha,
                     timeout=5, heartbeat=.01)
        self.assertEqual(result['status'], 'FAILED')
        self.assertEqual(result['exit_code'], 9)
        self.assertFalse(self.dest.exists())

    def test_timeout_kills_process_and_cleans_staging(self):
        self.driver('import time; time.sleep(60)\n')
        start = time.monotonic()
        result = run(self.elf, self.dest, self.tools, expected_sha256=self.sha,
                     timeout=.25, heartbeat=.05)
        self.assertEqual(result['status'], 'TIMED_OUT')
        self.assertLess(time.monotonic()-start, 4)
        self.assertFalse(self.dest.exists())
        self.assertEqual(list(self.root.glob('.edgeai-v31-*')), [])

    def test_existing_destination_is_never_overwritten(self):
        self.dest.mkdir()
        (self.dest/'important').write_text('preserve')
        with self.assertRaises(FileExistsError):
            run(self.elf, self.dest, self.tools, expected_sha256=self.sha)
        self.assertEqual((self.dest/'important').read_text(), 'preserve')

    def test_missing_manifest_fails_closed(self):
        self.driver('''
            import pathlib, sys
            dest = pathlib.Path(sys.argv[sys.argv.index('--destination')+1])
            dest.mkdir()
        ''')
        result = run(self.elf, self.dest, self.tools, expected_sha256=self.sha)
        self.assertEqual(result['status'], 'FAILED')
        self.assertFalse(self.dest.exists())

    def test_atomic_json_report(self):
        report = self.root / 'report.json'
        write_report(report, {'status': 'FAILED'})
        self.assertIn('FAILED', report.read_text())
        self.assertEqual(list(self.root.glob('.edgeai-report-*')), [])


if __name__ == '__main__':
    unittest.main()
