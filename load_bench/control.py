"""Bounded opposing torque, deterministic profiles and fail-closed readiness."""
from __future__ import annotations

from dataclasses import dataclass
import math
import random


class Interlock(RuntimeError):
    pass


def number(x):
    return type(x) in (int, float) and math.isfinite(x)


@dataclass(frozen=True)
class Limits:
    rated_torque_nm: float = 1.27
    max_torque_nm: float = .12
    max_power_w: float = 5.
    max_energy_j: float = 15.
    min_rpm: float = 80.
    max_rpm: float = 350.
    slew_nm_s: float = .12
    duration_s: float = 4.
    cycle_s: float = .5
    deadline_s: float = .45
    nis_limit: float = 25.

    def __post_init__(self):
        if not all(number(v) and v > 0 for v in self.__dict__.values()):
            raise ValueError("Limits must be finite and positive")
        if not self.min_rpm < self.max_rpm or self.deadline_s >= self.cycle_s:
            raise ValueError("Invalid speed/deadline envelope")
        # First-stage ceiling; raising these is a new commissioning revision.
        if self.max_rpm > 350 or self.max_torque_nm > .2 or self.max_power_w > 10 or self.duration_s > 5:
            raise ValueError("Outside first-stage low-speed qualification envelope")
        if self.duration_s < 3:
            raise ValueError("Profile requires two zero-load tails and an excitation interval")


PROFILES = ("zero", "step", "ramp", "sine", "prbs")


def requested_load(profile, t, limits, seed=20261122):
    if profile not in PROFILES or not number(t):
        raise ValueError("Unknown profile/invalid time")
    duration = limits.duration_s
    if t < 1 or t >= duration-1:
        return 0.
    x = (t-1) / max(.01, duration-2)
    amplitude = limits.max_torque_nm
    if profile == "zero":
        return 0.
    if profile == "step":
        return amplitude
    if profile == "ramp":
        return amplitude * min(2*x, 2*(1-x))
    if profile == "sine":
        return amplitude * (1-math.cos(2*math.pi*x)) / 2
    # Prespecified hold intervals. No row shuffling or outcome-selected seeds.
    rng = random.Random(seed)
    return amplitude * [rng.choice((.25, 1.)) for _ in range(32)][min(31, int((t-1)/.5))]


def bench_problem(s, expected_pair, expected_run=None, require_running=True):
    if not isinstance(s, dict):
        return "missing_bench_status"
    if [s.get("fw_build"), s.get("mc_fw_build")] != list(expected_pair):
        return "firmware_pair_changed"
    for key in ("mc_age_ms", "mc_current_age_ms"):
        limit = 300 if key == "mc_age_ms" else 750
        if not number(s.get(key)) or not 0 <= s[key] < limit:
            return "stale_"+key
    for key in ("mc_fault_current_mask", "mc_fault_occurred_mask", "estop"):
        if s.get(key) != 0:
            return "fault_or_missing_"+key
    if s.get("mc_current_zero_ready") != 1 or s.get("mc_current_telemetry_valid") != 1:
        return "current_not_ready"
    if s.get("mc_current_frozen") != 0:
        return "current_frozen"
    if not number(s.get("freq_cmd")) or not 0 < s["freq_cmd"] <= 5:
        return "frequency_outside_qualified_stage"
    if require_running and s.get("pwm") != 1:
        return "air_pwm_off"
    identity = (s.get("run_id"), s.get("run_start_ms"))
    if any(type(v) is not int or not 0 <= v < 2**32 for v in identity):
        return "missing_native_run_identity"
    if expected_run is not None and identity != tuple(expected_run):
        return "air_run_changed"
    return None


def readiness(config):
    q = config.get("qualification", {})
    missing = [name for name in (
        "motor_nameplate_checked", "driver_revision_checked", "mode_and_sign_tested",
        "parameter_readback_checked",
        "stop_chain_tested", "parking_brake_timing_tested", "coupling_and_guard_checked",
        "air_loaded_trial_authorized_and_qualified", "usb_isolation_checked") if q.get(name) is not True]
    limits = Limits(**config.get("limits", {}))
    red=config.get("red_board",{})
    stock=red.get("backend")=="stock_hid"
    if stock:
        if config.get("experiment_mode")!="supervised_bench":missing.append("stock_requires_supervised_bench")
        if q.get("red_board_output_permit_tested") is not True:missing.append("red_board_output_permit_tested")
        if q.get("regen_power_rating_is_continuous") is not True:missing.append("regen_power_rating_is_continuous")
    elif red.get("backend")=="watchdog_cdc":
        for field in ("mcu_confirmed","gpio_map_verified","firmware_installed_and_verified"):
            if red.get(field) is not True:missing.append("red_board_"+field)
        if red.get("expected_firmware_id")!="RNRWD_AT32F403RC_20261122":missing.append("red_board_firmware_identity")
        if q.get("independent_czero_watchdog_tested") is not True:missing.append("independent_czero_watchdog_tested")
    else:missing.append("red_board_backend")
    for name, minimum in (("validated_regen_power_w", limits.max_power_w),
                          ("validated_regen_energy_j", limits.max_energy_j)):
        if not number(q.get(name)) or q[name] < minimum:
            missing.append(name)
    if not number(q.get("actual_rated_torque_nm")) or not math.isclose(q["actual_rated_torque_nm"], limits.rated_torque_nm, rel_tol=.001):
        missing.append("actual_rated_torque_nm")
    if not stock and (not number(q.get("watchdog_measured_drop_s")) or not 0 < q["watchdog_measured_drop_s"] <= 1.2):
        missing.append("watchdog_measured_drop_s")
    if type(q.get("di_conducting_bit")) is not int or q["di_conducting_bit"] not in (0, 1):
        missing.append("di_conducting_bit")
    if type(q.get("do_conducting_bit")) is not int or q["do_conducting_bit"] not in (0, 1):
        missing.append("do_conducting_bit")
    if type(config.get("expected_algorithm")) is not int:
        missing.append("expected_algorithm")
    # P065/066=25%, P075=500 rpm; overspeed alarm is specified at 120%.
    hard_power = .25 * limits.rated_torque_nm * 600 * math.pi / 30
    hard_energy = limits.max_energy_j + hard_power * 1.2
    if not number(q.get("validated_regen_power_w")) or q["validated_regen_power_w"] < hard_power:
        missing.append("continuous_regen_power_envelope" if stock else "regen_power_including_dropout")
    # Stock I/O has no bounded host-loss timeout. Do not pretend a 1.2s energy
    # allowance covers it: require the hard-power envelope to be continuous.
    if not stock and (not number(q.get("validated_regen_energy_j")) or q["validated_regen_energy_j"] < hard_energy):
        missing.append("regen_energy_including_dropout")
    return missing


class LoadControl:
    def __init__(self, limits=Limits()):
        self.limits = limits
        self.energy_j = 0.
        self.last_magnitude = 0.
        self.direction = None
        self.tripped = None

    def trip(self, why):
        self.tripped = why
        self.last_magnitude = 0.
        raise Interlock(why)

    def update(self, requested_nm, rpm, dt, measured_torque_percent=0., nis=None):
        if self.tripped:
            raise Interlock("latched:"+self.tripped)
        if not all(number(x) for x in (requested_nm, rpm, dt, measured_torque_percent)) or dt <= 0:
            return self.trip("nonfinite_or_invalid_sample")
        if requested_nm < 0:
            return self.trip("negative_load_request")
        if dt > self.limits.cycle_s * 1.5:
            return self.trip("cycle_gap")
        if abs(rpm) > self.limits.max_rpm:
            return self.trip("overspeed")
        if abs(measured_torque_percent) > 27:
            return self.trip("measured_torque_exceeds_hard_cap")
        measured_power = abs(measured_torque_percent)*self.limits.rated_torque_nm/100*abs(rpm)*math.pi/30
        quantization_allowance = .02*self.limits.rated_torque_nm*self.limits.max_rpm*math.pi/30
        if measured_power > self.limits.max_power_w + quantization_allowance:
            return self.trip("measured_regen_power")
        if nis is not None and (not number(nis) or nis >= self.limits.nis_limit):
            return self.trip("observer_invalid")
        # Conservative trapezoid-free energy budget: charge the whole interval at
        # the larger of the last command and the current drive torque estimate.
        power = max(self.last_magnitude, abs(measured_torque_percent)*self.limits.rated_torque_nm/100) * self.limits.max_rpm*math.pi/30
        self.energy_j += power * dt
        if self.energy_j >= self.limits.max_energy_j:
            return self.trip("energy_budget")
        if abs(rpm) < self.limits.min_rpm:
            if self.last_magnitude:
                return self.trip("stall_or_low_speed")
            return 0
        direction = 1 if rpm > 0 else -1
        if self.direction is not None and direction != self.direction:
            return self.trip("rotation_reversed")
        self.direction = direction
        if measured_torque_percent * direction > 2:
            return self.trip("servo_is_motoring")
        magnitude = min(requested_nm, self.limits.max_torque_nm,
                        self.limits.max_power_w / (abs(rpm)*math.pi/30),
                        self.last_magnitude + self.limits.slew_nm_s * dt)
        # Round toward zero, never above a power/torque constraint.
        percent = math.floor(magnitude / self.limits.rated_torque_nm * 100 + 1e-10)
        self.last_magnitude = percent * self.limits.rated_torque_nm/100
        return -direction * percent


def expected_parameters(config):
    return {4: 2, 26: 1, 65: 25, 66: -25, 75: 500, 77: 0, 78: 400,
            98: 0, 100: 1, 101: -8, 102: -8, 103: 0,
            108: 2, 109: 3, 110: 0, 111: 8,
            120: 0, 121: 0, 122: 0, 123: 0, 124: 0,
            146: 0, 147: 0, 148: 0, 181: config["modbus"]["unit"], 182: 2, 183: 1}


def parameter_mismatches(snapshot, config):
    return {str(k): {"expected": v, "actual": snapshot.get(str(k))}
            for k, v in expected_parameters(config).items() if snapshot.get(str(k)) != v}
