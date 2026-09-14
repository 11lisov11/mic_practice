"""Experimental terminal-energy budget, conditional on explicit error bounds.

The budget counts positive interval-mean excess during probes and recovery,
not the continuous positive part, and not excess during accepted holding.
This is not a hardware safety certificate or a learned policy. Counterfactual
baseline power is not measured online. Its drift bound and the recovery power
bound are assumptions which must be independently validated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
import math

from control.air56b2_dynamic_probe import (
    DynamicProbeConfig, DynamicProbeSupervisor, _finite_real,
)


@dataclass(frozen=True)
class ProbeBudgetConfig:
    max_probe_excess_j: float = 8.0
    power_error_bound_w: float = 1.0
    baseline_drift_w_per_s: float = 0.5
    gain_deterioration_w_per_s: float = 0.5
    excess_power_cap_w: float = 10.0
    recovery_settle_s: float = 0.27
    hold_until_s: float = 6.0
    minimum_net_gain_j: float = 0.1

    def __post_init__(self):
        for field in fields(self):
            value = _finite_real(field.name, getattr(self, field.name))
            if value < 0:
                raise ValueError(f"{field.name} must be nonnegative")
            object.__setattr__(self, field.name, value)
        if self.excess_power_cap_w <= 0 or self.hold_until_s <= 0:
            raise ValueError("power cap and horizon must be positive")


def net_gain_lower_bound(gain_w, hold_s, spent_upper_j, recovery_upper_j, drift_w_per_s):
    """Integral of g(t) >= gain_w - drift*t, less probe/recovery costs.

    A negative future gain is NOT clipped away. This inequality concerns input
    energy at motor terminals; useful work and stored energy need separate QA.
    """
    values = [gain_w, hold_s, spent_upper_j, recovery_upper_j, drift_w_per_s]
    values = [_finite_real("bound input", v) for v in values]
    gain, hold, spent, recovery, drift = values
    if min(hold, spent, recovery, drift) < 0:
        raise ValueError("time, costs and drift must be nonnegative")
    result = gain * hold - 0.5 * drift * hold**2 - spent - recovery
    if not math.isfinite(result):
        raise ValueError("nonfinite net gain bound")
    return result


class BudgetedDynamicProbeSupervisor(DynamicProbeSupervisor):
    """Existing analytic probe sequence + budget and finite-horizon gates.

    Ablations disable only the respective gate, not accounting or the scheduled
    return. No plant state, paired baseline trajectory or future load is input.
    ``hold_until_s`` is a declared task deadline, NOT a predicted stable regime.
    All error/drift/recovery bounds are assumed, not inferred from a sample SD.
    """
    def __init__(self, config: DynamicProbeConfig, budget: ProbeBudgetConfig,
                 *, budget_gate=True, payback_gate=True):
        super().__init__(config)
        if not isinstance(budget, ProbeBudgetConfig):
            raise TypeError("budget must be ProbeBudgetConfig")
        self.budget = budget
        self.budget_gate = budget_gate
        self.payback_gate = payback_gate
        self.spent_upper_j = 0.0
        self.gain_lower_w = None
        self.net_gain_lower_j = None
        self.ever_committed = False
        self.payback_status = "not_evaluated"
        self.bounds_valid = True
        self.bound_failures = set()
        self.budget_events = []
        self._anchor_power = None
        self._anchor_time = None
        self._budget_last_time = None
        self._recovery_until = None
        self._return_arrived_s = None
        self._end_accounting = False

    def _bound_failure(self, reason):
        self.bounds_valid = False
        self.bound_failures.add(reason)

    def recovery_s(self, id_a=None):
        reference = self.id_ref_a if id_a is None else id_a
        return (abs(reference - self.config.baseline_id_a) / self.config.slew_a_per_s
                + self.budget.recovery_settle_s)

    def _reject(self, time_s, reason, *, abort=True):
        if not self.rejected:
            self._recovery_until = time_s + self.recovery_s()
            self._return_arrived_s = None
            if self.ever_committed:
                if reason != "scheduled_return":
                    self.payback_status = "invalidated_by_early_return"
                    self._bound_failure("hold_interrupted")
                else:
                    self.payback_status = "scheduled_holding_ended_conditional_only"
        super()._reject(time_s, reason, abort=abort)

    def _record(self, time_s, reason, **extra):
        self.budget_events.append(dict(time_s=time_s, reason=reason,
                                      spent_upper_j=self.spent_upper_j, **extra))

    def _accept_window(self, window, time_s):
        phase = self.phase
        if phase == "baseline_repeat" and self._anchor_power is not None:
            age = time_s - self._anchor_time
            allowed = (2 * self.budget.power_error_bound_w
                       + self.budget.baseline_drift_w_per_s * age)
            if abs(window.measurement.power_w - self._anchor_power) > allowed:
                self._bound_failure("observed_baseline_drift")
        super()._accept_window(window, time_s)
        if phase == "baseline":
            self._anchor_power = window.measurement.power_w
            # Oldest sample gives the largest age for a conservative drift bound.
            self._anchor_time = window.samples[0].time_s
            reserve = self.budget.excess_power_cap_w * (
                self.recovery_s(self.config.low_id_a) + self.config.dt_s)
            if self.budget_gate and reserve > self.budget.max_probe_excess_j:
                self._record(time_s, "entry_reserve", reserve_j=reserve)
                self._reject(time_s, "budget_entry_reserve", abort=False)
                # No changed reference was issued, so no experimental return is needed.
                self._end_accounting = True
                self._recovery_until = time_s
                self._return_arrived_s = time_s
        if phase == "candidateverify" and self.phase == "committed":
            baseline_windows = [w for w in self.windows
                                if w.phase in ("baseline", "baseline_repeat")]
            # Samples describe the preceding interval. A one-period age bound
            # covers that delay; rho_g must also hold THROUGH the validation window.
            mean_age_s = (sum(time_s - sample.time_s for sample in window.samples)
                          / len(window.samples) + self.config.dt_s)
            self.gain_lower_w = min(
                w.measurement.power_w - window.measurement.power_w
                - 2 * self.budget.power_error_bound_w
                - self.budget.baseline_drift_w_per_s * (time_s - w.samples[0].time_s)
                for w in baseline_windows) - self.budget.gain_deterioration_w_per_s * mean_age_s
            hold = max(0., self.budget.hold_until_s - time_s
                       - self.recovery_s(self.candidate_id_a) - 2*self.config.dt_s)
            recovery = self.budget.excess_power_cap_w * (
                self.recovery_s(self.candidate_id_a) + self.config.dt_s)
            self.net_gain_lower_j = net_gain_lower_bound(
                self.gain_lower_w, hold, self.spent_upper_j, recovery,
                self.budget.gain_deterioration_w_per_s)
            accepted = not self.payback_gate or (
                self.bounds_valid and hold > 0
                and self.net_gain_lower_j > self.budget.minimum_net_gain_j)
            self._record(time_s, "payback_accept" if accepted else "payback_decline",
                         gain_lower_w=self.gain_lower_w, hold_s=hold,
                         validation_mean_age_bound_s=mean_age_s,
                         recovery_upper_j=recovery, net_gain_lower_j=self.net_gain_lower_j)
            if accepted:
                self.ever_committed = True
                self.payback_status = "conditional_projection" if self.payback_gate else "gate_disabled"
            else:
                self.payback_status = "declined"
                # The inherited power test passed, but the complete gate did not.
                # Do not leave a fictitious committed transition in the event log.
                if self._events[-1].kind == "stage_started" and self._events[-1].phase == "committed":
                    self._events.pop()
                self.phase = "candidateverify"
                self._reject(time_s, "payback_not_established", abort=False)

    def step(self, time_s, measured_power_w, measured_current_peak_a,
             measured_voltage_peak_v, measured_speed_rad_s, reference_speed_rad_s,
             voltage_limit_v=None):
        time_s = _finite_real("time_s", time_s)
        if time_s < 0 or (self._last_time_s is not None and time_s <= self._last_time_s):
            raise ValueError("time_s must be nonnegative and strictly increasing")
        elapsed = 0. if self._budget_last_time is None else time_s - self._budget_last_time
        self._budget_last_time = time_s
        if elapsed > self.config.dt_s * (1 + 1e-9):
            self._bound_failure("sample_gap")
        try:
            power = _finite_real("measured_power_w", measured_power_w)
        except ValueError:
            power = None
            self._bound_failure("invalid_power")
        active = self._anchor_power is not None and not self._end_accounting
        if active and self.phase != "committed":
            if power is None:
                upper_w = self.budget.excess_power_cap_w
            else:
                upper_w = max(0., power - self._anchor_power
                              + 2 * self.budget.power_error_bound_w
                              + self.budget.baseline_drift_w_per_s * (time_s - self._anchor_time))
                # Do not silently clip evidence that contradicts the assumed cap.
                if upper_w > self.budget.excess_power_cap_w:
                    self._bound_failure("excess_cap_not_established")
            self.spent_upper_j += upper_w * elapsed
            if not math.isfinite(self.spent_upper_j):
                raise ValueError("nonfinite accumulated budget")
        if self.phase not in ("waiting", "rollback", "rejected"):
            return_time = self.recovery_s()
            if self.phase == "committed" and self.payback_gate and not self.bounds_valid:
                self._reject(time_s, "payback_assumptions_invalid")
            elif time_s + return_time + 2*self.config.dt_s >= self.budget.hold_until_s:
                self._record(time_s, "scheduled_return")
                self._reject(time_s, "scheduled_return", abort=False)
            elif active and self.phase != "committed" and self.budget_gate:
                # One future control step and its possible added slew both need reserve.
                reserve = self.budget.excess_power_cap_w * (return_time + 2*self.config.dt_s)
                if (not self.bounds_valid
                        or self.spent_upper_j + reserve > self.budget.max_probe_excess_j):
                    self._record(time_s, "budget_stop", reserve_j=reserve)
                    self._reject(time_s, "probe_energy_budget", abort=False)
        result = super().step(time_s, measured_power_w, measured_current_peak_a,
                              measured_voltage_peak_v, measured_speed_rad_s,
                              reference_speed_rad_s, voltage_limit_v)
        if result.phase == "rejected" and self._recovery_until is not None:
            if self._return_arrived_s is None:
                self._return_arrived_s = time_s
                self._recovery_until = max(self._recovery_until,
                                          time_s + self.budget.recovery_settle_s)
            if time_s + 1e-12 < self._recovery_until:
                result = replace(result, completed=False)
            else:
                self._end_accounting = True
        return result

    def summary(self):
        return dict(config=asdict(self.budget), budget_gate=self.budget_gate,
                    payback_gate=self.payback_gate, spent_upper_j=self.spent_upper_j,
                    ever_committed=self.ever_committed, gain_lower_w=self.gain_lower_w,
                    payback_status=self.payback_status,
                    net_gain_lower_j=self.net_gain_lower_j, bounds_valid=self.bounds_valid,
                    anchor_power_w=self._anchor_power, anchor_time_s=self._anchor_time,
                    bound_failures=sorted(self.bound_failures), events=self.budget_events,
                    budget_scope="positive_interval_mean_excess_probe_and_return_only",
                    certificate="conditional_assumptions_only_not_hardware_validated")
