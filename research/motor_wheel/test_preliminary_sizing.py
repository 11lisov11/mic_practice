"""Independent physical identities and the limiting inverter case."""

import copy
import json
import math
from pathlib import Path
import unittest

from preliminary_sizing import calculate, electrical_screen, road_load


class SizingTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(Path(__file__).with_name("sizing_inputs.json").read_text(encoding="utf-8"))

    def test_zero_resistance_has_only_translational_inertia(self):
        vehicle = dict(self.config["vehicle"], rolling_coefficient=0.0, drag_area_m2=0.0)
        row = road_load(vehicle, 18.0, 0.0, 0.5)
        self.assertAlmostEqual(row["wheel_force_n"], 60.0)
        self.assertAlmostEqual(row["wheel_mechanical_power_w"], 300.0)
        self.assertAlmostEqual(row["wheel_torque_nm"], 15.24)

    def test_grade_is_percent_not_degrees(self):
        vehicle = dict(self.config["vehicle"], rolling_coefficient=0.0, drag_area_m2=0.0)
        row = road_load(vehicle, 10.0, 5.0)
        expected = 120.0 * 9.80665 * 0.05 / math.sqrt(1 + 0.05**2)
        self.assertAlmostEqual(row["grade_force_n"], expected)

    def test_circumference_and_power_are_consistent(self):
        row = road_load(self.config["vehicle"], 25.0, 0.0)
        self.assertAlmostEqual(row["wheel_rpm"] * math.pi * 0.508 / 60, 25 / 3.6)
        self.assertAlmostEqual(row["wheel_torque_nm"] * row["wheel_rpm"] * 2 * math.pi / 60,
                               row["wheel_mechanical_power_w"])
        self.assertAlmostEqual(row["wheel_mechanical_power_w"], 245.65813143004118)

    def test_500_w_is_not_accepted_as_a_15_a_rating(self):
        row = electrical_screen(36.0, 500.0, self.config["inverter_screen"], self.config["energy"])
        self.assertGreater(row["optimistic_line_current_rms_a"], 20.0)
        self.assertFalse(row["within_board_nominal_rms_current"])
        self.assertFalse(row["within_proposed_software_peak"])
        self.assertFalse(row["is_motor_or_short_term_rating_validation"])

    def test_five_percent_grade_at_25_kmh_exceeds_power_target(self):
        report = calculate(self.config)
        row = next(r for r in report["road_cases"] if r["grade_pct"] == 5 and r["speed_kmh"] == 25 and r["acceleration_m_s2"] == 0)
        self.assertGreater(row["wheel_mechanical_power_w"], 650)
        self.assertFalse(row["within_requested_continuous_envelope"])
        self.assertFalse(row["within_tentative_peak_envelope"])

    def test_acceleration_has_no_trip_range_claim(self):
        for row in calculate(self.config)["road_cases"]:
            if row["acceleration_m_s2"]:
                self.assertNotIn("conditional_steady_range_km", row)

    def test_invalid_efficiency_and_nonfinite_mass_are_rejected(self):
        config = copy.deepcopy(self.config)
        config["energy"]["motor_efficiency_assumption"] = 1.01
        with self.assertRaises(ValueError):
            calculate(config)
        vehicle = dict(self.config["vehicle"], gross_mass_kg=float("nan"))
        with self.assertRaises(ValueError):
            road_load(vehicle, 25.0, 0.0)


if __name__ == "__main__":
    unittest.main()
