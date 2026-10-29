"""Pure structural tests; no original game source or ELF fixture required."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from aarch64_init_chain_lifter import lift


def fixture():
    specs = [
        ('stp', 'x29, x30, [sp, #-0x10]!'), ('mov', 'x29, sp'),
        ('adrp', 'x1, 0x2000'), ('add', 'x1, x1, #0x10'),
        ('mov', 'w0, #0x2'), ('bl', '0x100'),
        ('adrp', 'x1, 0x2000'), ('add', 'x1, x1, #0x20'),
        ('mov', 'w0, #0x2'), ('bl', '0x100'),
        ('mov', 'x0, #0x0'), ('bl', '0x104'), ('bl', '0x108'),
        ('mov', 'w0, #0x0'), ('bl', '0x4000'),
        ('adrp', 'x1, 0x4000'), ('add', 'x1, x1, #0x80'),
        ('mov', 'w0, #0x2'), ('bl', '0x10c'),
        ('ldp', 'x29, x30, [sp], #0x10'), ('ret', '')
    ]
    rows = [(0x3000 + 4 * i, op, args) for i, (op, args) in enumerate(specs)]
    return rows, (0x2000, b'\0' * 0x10 + b'hello\0' + b'\0' * 10 + b'world\0'), {
        0x100: '__printf_chk', 0x104: 'time', 0x108: 'srand', 0x10c: 'signal'
    }, {0x4000, 0x4080}


class InitChainTests(unittest.TestCase):
    def test_valid_chain(self):
        src, report = lift(*fixture())
        self.assertIn('recovered_3000()', src)
        self.assertIn('recovered_4000(0u)', src)
        self.assertIn('recovered_4080', src)
        self.assertEqual(report['instruction_count'], 21)
        self.assertFalse(report['behaviorally_validated'])

    def test_unknown_import_rejected(self):
        rows, ro, plt, entries = fixture()
        plt[0x104] = 'rand'
        with self.assertRaisesRegex(ValueError, 'time@plt'):
            lift(rows, ro, plt, entries)

    def test_wrong_seed_rejected(self):
        rows, ro, plt, entries = fixture()
        rows[10] = (rows[10][0], 'mov', 'x0, #0x1')
        with self.assertRaisesRegex(ValueError, 'unsupported instruction'):
            lift(rows, ro, plt, entries)

    def test_unknown_terminal_rejected(self):
        rows, ro, plt, entries = fixture()
        entries.remove(0x4000)
        with self.assertRaisesRegex(ValueError, 'terminal callback'):
            lift(rows, ro, plt, entries)

    def test_unknown_handler_rejected(self):
        rows, ro, plt, entries = fixture()
        entries.remove(0x4080)
        with self.assertRaisesRegex(ValueError, 'signal handler'):
            lift(rows, ro, plt, entries)

    def test_printf_format_rejected(self):
        rows, ro, plt, entries = fixture()
        ro = (ro[0], ro[1].replace(b'hello', b'%dllo'))
        with self.assertRaisesRegex(ValueError, 'format arguments'):
            lift(rows, ro, plt, entries)

    def test_wrong_frame_rejected(self):
        rows, ro, plt, entries = fixture()
        rows[0] = (rows[0][0], 'stp', 'x29, x30, [sp, #-0x20]!')
        with self.assertRaisesRegex(ValueError, 'unsupported instruction'):
            lift(rows, ro, plt, entries)

    def test_trailing_instruction_rejected(self):
        rows, ro, plt, entries = fixture()
        rows.append((0x3000 + 4 * len(rows), 'nop', ''))
        with self.assertRaisesRegex(ValueError, 'trailing'):
            lift(rows, ro, plt, entries)

    def test_missing_instruction_rejected(self):
        rows, ro, plt, entries = fixture()
        rows.pop(5)
        with self.assertRaisesRegex(ValueError, 'noncontiguous'):
            lift(rows, ro, plt, entries)

    def test_unknown_opcode_rejected(self):
        rows, ro, plt, entries = fixture()
        rows[11] = (rows[11][0], 'blr', 'x0')
        with self.assertRaisesRegex(ValueError, 'unsupported instruction'):
            lift(rows, ro, plt, entries)


if __name__ == '__main__':
    unittest.main()
