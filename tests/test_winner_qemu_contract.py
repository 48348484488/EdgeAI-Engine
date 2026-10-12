"""Fail-closed checks of the ARM/QEMU validation contract (not simulated success)."""
import sys
import unittest
import tempfile
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from validate_winner_qemu import require_toolchain, require_linux_arm32

class QemuContractTests(unittest.TestCase):
    def test_missing_tools_do_not_count_as_executed(self):
        with self.assertRaisesRegex(RuntimeError,'NOT RUN; missing tools'):
            require_toolchain(resolve=lambda name: None)

    def test_accept_real_clang_arm32_object(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/"probe.o"
            subprocess.run(["clang","--target=armv7-none-eabi","-marm","-c",
                            "-x","c","-o",str(out),"-"],
                           input="int probe(void){return 42;}\n",
                           text=True,check=True,capture_output=True)
            require_linux_arm32(out)

    def test_refuse_non_arm_binary(self):
        with self.assertRaisesRegex(RuntimeError,'not a little-endian ARM32 ELF'):
            require_linux_arm32(Path(__file__))

if __name__ == '__main__': unittest.main()
