"""Fail-closed checks of the ARM/QEMU validation contract (not simulated success)."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from validate_winner_qemu import require_toolchain, require_linux_arm32

class QemuContractTests(unittest.TestCase):
    def test_missing_tools_do_not_count_as_executed(self):
        with self.assertRaisesRegex(RuntimeError,'NOT RUN; missing tools'):
            require_toolchain(resolve=lambda name: None)

    def test_refuse_non_arm_binary(self):
        with self.assertRaisesRegex(RuntimeError,'not a little-endian ARM32 ELF'):
            require_linux_arm32(Path(__file__))

if __name__ == '__main__': unittest.main()
