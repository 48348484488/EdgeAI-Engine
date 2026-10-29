import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from edgeai_2048_call_closure import audit, generated_functions

SHA = 'a' * 64


def cfg(calls):
    return {'source_read': False, 'behaviorally_validated': False,
            'binary_sha256': SHA, 'start': '0x1000', 'end_exclusive': '0x1040', 'calls': calls}


def call(pc, target, symbol=None, indirect=False):
    return {'pc': hex(pc), 'target': hex(target) if target is not None else None,
            'symbol': symbol, 'indirect': indirect}


class ClosureTests(unittest.TestCase):
    def test_classification(self):
        rows = [call(0x1000, 0x2000, '.text'), call(0x1004, 0x3000, '.text'),
                call(0x1008, 0x800, 'getchar@plt'), call(0x100c, None, indirect=True)]
        r = audit(cfg(rows), {0x2000: {'file': 'candidate_2000.cpp'}})
        self.assertEqual((r['calls_to_generated_cpp'], r['calls_missing_internal_cpp'],
                          r['calls_to_external_plt'], r['indirect_unresolved_calls']), (1, 1, 1, 1))
        self.assertEqual(r['missing_internal_targets'], ['0x3000'])
        self.assertFalse(r['complete'])

    def test_repeated_calls_counted_once_as_missing_target(self):
        r = audit(cfg([call(0x1000, 0x3000), call(0x1004, 0x3000)]), {})
        self.assertEqual(r['calls_missing_internal_cpp'], 2)
        self.assertEqual(r['missing_internal_targets'], ['0x3000'])

    def test_wrong_elf_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            audit(cfg([]), {}, 'b' * 64)

    def test_source_read_claim_rejected(self):
        c = cfg([]); c['source_read'] = True
        with self.assertRaisesRegex(ValueError, 'source-blind'):
            audit(c, {})

    def test_missing_direct_target_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing target'):
            audit(cfg([call(0x1000, None)]), {})

    def test_generated_source_must_export_matching_function(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'candidate_2000.cpp'
            p.write_text('extern "C" int recovered_2001() { return 1; }')
            with self.assertRaisesRegex(ValueError, 'matching exported'):
                generated_functions(Path(d))
            p.write_text('extern "C" int recovered_2000() { return 1; }')
            self.assertIn(0x2000, generated_functions(Path(d)))

    def test_prototype_only_does_not_count_as_recovered(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'candidate_2000.cpp'
            p.write_text('extern "C" int recovered_2000();')
            with self.assertRaisesRegex(ValueError, 'matching exported'):
                generated_functions(Path(d))
            p.write_text('extern "C" int recovered_2000();\n'
                         'extern "C" int recovered_2000() { return 1; }')
            self.assertIn(0x2000, generated_functions(Path(d)))

    def test_main_hook_is_not_a_native_export(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'candidate_401758.cpp'
            p.write_text('int candidate_401758(const Hooks&, size_t);')
            with self.assertRaisesRegex(ValueError, 'matching exported'):
                generated_functions(Path(d))

    def test_dependency_gate_fails_when_missing(self):
        result = audit(cfg([call(0x1000, 0x2000)]), {})
        self.assertFalse(result['dependency_closure_complete'])
        self.assertFalse(result['native_link_tested'])

    def test_dependency_gate_does_not_claim_whole_game(self):
        result = audit(cfg([call(0x1000, 0x2000)]), {0x2000: {'file': 'candidate_2000.cpp'}})
        self.assertTrue(result['dependency_closure_complete'])
        self.assertFalse(result['native_link_tested'])
        self.assertFalse(result['complete'])

    def test_no_generated_directory_rejected(self):
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            generated_functions(Path('/definitely/not/an/edgeai/path'))

    def test_malformed_call_site_rejected(self):
        with self.assertRaisesRegex(ValueError, 'malformed call site'):
            audit(cfg([{'pc':'invalid', 'target':'0x2000'}]), {})

    def test_indirect_call_with_static_target_rejected(self):
        with self.assertRaisesRegex(ValueError, 'must not claim'):
            audit(cfg([call(0x1000, 0x2000, indirect=True)]), {})


if __name__ == '__main__':
    unittest.main()
