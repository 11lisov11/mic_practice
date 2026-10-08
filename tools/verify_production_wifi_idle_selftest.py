import unittest
from verify_production_wifi_idle import safe_zero_bus, uart_progress


class IdleGuardTests(unittest.TestCase):
    def state(self, **changes):
        value = dict(vdc=0, bp_age_ms=20, bp_vbus_valid=1, state="SAFE",
                     pwm=0, hmi_hv_armed=0, bp_status=9)
        value.update(changes)
        return value

    def test_valid_discharged_faulted_state(self):
        self.assertTrue(safe_zero_bus(self.state()))

    def test_rejects_invalid_measurements(self):
        for vdc in (float('nan'), float('inf'), -1, 3, None, "unknown"):
            with self.subTest(vdc=vdc):
                self.assertFalse(safe_zero_bus(self.state(vdc=vdc)))

    def test_rejects_unsafe_or_stale_state(self):
        for change in (dict(pwm=1), dict(hmi_hv_armed=1), dict(bp_status=0x29),
                       dict(bp_status=0x0B), dict(bp_age_ms=300), dict(bp_age_ms=-1),
                       dict(bp_vbus_valid=0), dict(state="VF_RUN")):
            with self.subTest(change=change):
                self.assertFalse(safe_zero_bus(self.state(**change)))

    def test_missing_fields_fail_closed(self):
        for key in self.state():
            value = self.state()
            del value[key]
            self.assertFalse(safe_zero_bus(value), key)

    def test_uart_progress_and_counter_saturation(self):
        self.assertTrue(uart_progress([self.state(bp_good=10, bp_seq=7),
                                      self.state(bp_good=20, bp_seq=17)]))
        self.assertTrue(uart_progress([self.state(bp_good=65535, bp_seq=255),
                                      self.state(bp_good=65535, bp_seq=0),
                                      self.state(bp_good=65535, bp_seq=255)]))
        self.assertFalse(uart_progress([self.state(bp_good=65535, bp_seq=7)] * 3))
        self.assertFalse(uart_progress([self.state(bp_good=10, bp_seq=7),
                                       self.state(bp_good=10, bp_seq=8)]))
        self.assertFalse(uart_progress([self.state(bp_good=65535, bp_seq=7),
                                       self.state(bp_good=65535, bp_seq=8, bp_age_ms=1000)]))
        self.assertFalse(uart_progress([self.state(bp_good=65535, bp_seq=7),
                                       self.state(bp_good=65535, bp_seq=300)]))


if __name__ == '__main__':
    unittest.main()
