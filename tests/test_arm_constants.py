"""Tests for bounded ARM32 constant propagation."""
import importlib.util
from pathlib import Path
import struct
import unittest

path = Path(__file__).resolve().parents[1] / "tools" / "arm_constants.py"
spec = importlib.util.spec_from_file_location("arm_constants", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def elf(words):
    data = bytearray(0x100 + 4 * len(words))
    data[:16] = b"\x7fELF" + bytes([1, 1, 1]) + bytes(9)
    struct.pack_into("<HHIIIIIHHHHHH", data, 16,
                     2, 40, 1, 0x1000, 52, 0, 0, 52, 32, 1, 0, 0, 0)
    struct.pack_into("<IIIIIIII", data, 52,
                     1, 0x100, 0x1000, 0, len(words)*4, len(words)*4, 5, 4)
    for index, word in enumerate(words):
        struct.pack_into("<I", data, 0x100 + index*4, word)
    return bytes(data)


class PropagationTests(unittest.TestCase):
    def test_arithmetic_and_comparison(self):
        result = module.propagate(elf([
            0xe3a00005,  # mov r0, #5
            0xe2800003,  # add r0, r0, #3
            0xe3500008,  # cmp r0, #8
            0xe12fff1e,  # bx lr
        ]), 0x1000)
        self.assertEqual(result["known_registers"]["r0"], "0x8")
        self.assertIs(result["trace"][2]["equal"], True)

    def test_unknown_source_is_not_assumed_zero(self):
        result = module.propagate(elf([0xe2810004, 0xe12fff1e]), 0x1000)
        self.assertNotIn("r0", result["known_registers"])

    def test_stops_on_unsupported(self):
        result = module.propagate(elf([0xe3a00005, 0xe5901000, 0xe2800001]), 0x1000)
        self.assertEqual(result["known_registers"]["r0"], "0x5")
        self.assertEqual(result["trace"][-1]["status"], "stopped_at_unknown_or_control")

    def test_stops_on_branch(self):
        result = module.propagate(elf([0xe3a00005, 0xea000000, 0xe2800001]), 0x1000)
        self.assertEqual(result["known_registers"]["r0"], "0x5")

    def test_reject_unaligned(self):
        with self.assertRaises(module.sem.cfg.arm.ScanError):
            module.propagate(elf([0xe12fff1e]), 0x1001)


if __name__ == "__main__":
    unittest.main()
