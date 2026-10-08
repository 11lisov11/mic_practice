import tempfile
import unittest
from pathlib import Path

from wifi_stop_tail_probe import DHCSR, GPIOA, GPIOB, TIM1, hardware_off, parse_registers, tail_summary


def safe_registers():
    return {TIM1: 0, TIM1 + 0x20: 0, TIM1 + 0x44: 0, DHCSR: 1 << 17,
            GPIOA: sum(1 << (2 * p) for p in (7, 8, 9, 10)), GPIOB: 5,
            GPIOA + 4: 0, GPIOB + 4: 0, GPIOA + 0x10: 0, GPIOB + 0x10: 0,
            GPIOA + 0x14: 0, GPIOB + 0x14: 0}


class ProbeTests(unittest.TestCase):
    def test_register_parser(self):
        r = parse_registers("Read address 0x40012C00\n0x40012C00 : 00000000 00000012\n0xE000EDF0 : 00020003\n")
        self.assertEqual(r, {TIM1: 0, TIM1 + 4: 18, DHCSR: 0x20003})

    def test_halted_low(self):
        self.assertTrue(hardware_off(safe_registers())["pass"])

    def test_fail_closed_each_register(self):
        for address in safe_registers():
            with self.subTest(address=address):
                r = safe_registers()
                del r[address]
                self.assertFalse(hardware_off(r)["pass"])

    def test_rejects_running_enabled_or_high(self):
        for address, value in ((TIM1, 1), (TIM1 + 0x20, 0x555), (TIM1 + 0x44, 0x8000),
                               (DHCSR, 0), (GPIOA, 0), (GPIOB, 0), (GPIOA + 4, 1 << 7),
                               (GPIOA + 0x14, 1 << 8), (GPIOB + 0x10, 1)):
            with self.subTest(address=address):
                r = safe_registers()
                r[address] = value
                self.assertFalse(hardware_off(r)["pass"])

    def test_tail_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "wave.csv"
            p.write_text("Time [s],Channel 0,Channel 1,Channel 2,Channel 3,Channel 4,Channel 5\n"
                         "0,1,0,1,0,1,0\n0.000256,0,0,0,0,0,0\n0.1,0,0,0,0,0,0\n")
            r = tail_summary(p, 2_000_000)
            self.assertEqual(r["last_edge_sample"], 512)
            self.assertEqual(r["edge_count"], 3)
            self.assertTrue(r["all_final_low"])


if __name__ == "__main__":
    unittest.main()
