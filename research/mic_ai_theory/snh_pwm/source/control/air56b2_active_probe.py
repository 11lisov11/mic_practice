"""Measurement-only A-B-A probing with empirical cost and decision information.

This is an experimental design heuristic, NOT a certified energy budget or a
motor identification algorithm. Finite concave gain hypotheses, linear baseline
interpolation and cost transfer across amplitudes are explicit working priors.
Power/speed settling is observable; rotor-flux recovery is not certified.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, fields, replace
import math

from control.air56b2_dynamic_probe import (
    DynamicProbeConfig, DynamicProbeSupervisor, DynamicProbeEvent,
    DynamicProbeSample, _finite_real,
)


@dataclass(frozen=True)
class ActiveProbeConfig:
    hold_until_s: float = 6.0
    gain_error_floor_w: float = 1.0
    max_baseline_slope_w_per_s: float = 4.0
    decision_regret_w: float = 2.0
    prior_excess_w: float = 10.0
    cost_floor_j: float = 0.1
    cost_multiplier: float = 1.5
    max_estimated_cost_j: float = 8.0
    minimum_net_gain_j: float = 0.1
    return_margin_s: float = 0.15
    max_probes: int = 2

    def __post_init__(self):
        for f in fields(self):
            value = _finite_real(f.name, getattr(self, f.name))
            if value < 0:
                raise ValueError(f"{f.name} must be nonnegative")
            if f.name == "max_probes":
                if value != int(value) or not 1 <= value <= 4:
                    raise ValueError("max_probes must be an integer in [1, 4]")
                value = int(value)
            object.__setattr__(self, f.name, value)
        if min(self.hold_until_s, self.gain_error_floor_w, self.cost_floor_j,
               self.prior_excess_w, self.cost_multiplier) <= 0:
            raise ValueError("horizon, uncertainty and cost scales must be positive")


def window_point(window):
    """Observation time is the mean of the preceding interval midpoints."""
    samples = window.samples
    dt = samples[1].time_s - samples[0].time_s
    return (math.fsum(s.time_s for s in samples) / len(samples) - dt / 2,
            window.measurement.power_w)


def interpolated_power(before, after, time_s):
    t0, p0 = before
    t1, p1 = after
    if t1 <= t0 or not all(math.isfinite(v) for v in (*before, *after, time_s)):
        raise ValueError("finite, ordered baseline anchors required")
    return p0 + (p1 - p0) * ((time_s - t0) / (t1 - t0))


def bracket_estimate(before, probe, after, intervals, return_started_s, error_floor_w):
    """Retrospective A-B-A estimate, not a causal counterfactual measurement.

    intervals = (interval_end, dt, measured_mean_power). Positive interval
    excess includes the whole excursion. Endpoint windows permit a short
    extrapolation at the end, which is logged rather than hidden. The empirical
    error width is not a confidence level and does not prove affine drift.
    """
    a, b, c = window_point(before), window_point(probe), window_point(after)
    if not a[0] < b[0] < c[0]:
        raise ValueError("baseline/probe/return windows must be ordered")
    gain = interpolated_power(a, c, b[0]) - b[1]
    width = error_floor_w + max(w.power_std_w + w.power_endpoint_drift_w
                                for w in (before, probe, after))
    excess = signed = recovery = extrapolated_s = 0.
    for end, dt, power in intervals:
        if dt <= 0 or not all(math.isfinite(v) for v in (end, dt, power)):
            raise ValueError("invalid interval")
        mid = end - dt / 2
        delta = power - interpolated_power(a, c, mid)
        signed += delta * dt
        excess += max(0., delta) * dt
        if end > return_started_s:
            recovery += max(0., delta) * dt
        if not a[0] <= mid <= c[0]:
            extrapolated_s += dt
    if not all(math.isfinite(v) for v in (gain, width, excess, signed, recovery)):
        raise ValueError("nonfinite bracket estimate")
    return dict(gain_w=gain, error_width_w=width, gain_lower_heuristic_w=gain-width,
                excess_j=excess, signed_excess_j=signed, recovery_excess_j=recovery,
                baseline_slope_w_per_s=(c[1]-a[1])/(c[0]-a[0]),
                baseline_before=a, baseline_after=c, probe_point=b,
                extrapolated_s=extrapolated_s)


def gain_hypotheses(ids, baseline):
    """Local response hypotheses, not electrical parameters from the nameplate."""
    span = max(abs(i - baseline) for i in ids)
    x = [(i - baseline) / span for i in ids]
    return tuple(tuple(slope*z - curvature*z*z for z in x)
                 for slope in range(-24, 25, 2) for curvature in range(0, 17, 2))


def decision_information(hypotheses, index, resolution_w):
    """Mutual information of quantized outcomes and the best-action label.

    Equal finite-hypothesis weights are a design heuristic, not calibrated
    probabilities. Baseline (zero gain) is always an available decision.
    """
    if not hypotheses or resolution_w <= 0:
        raise ValueError("nonempty hypotheses and positive resolution required")
    labels = [max(range(len(h)+1), key=lambda j: 0. if j == 0 else h[j-1])
              for h in hypotheses]
    bins = [math.floor(h[index] / resolution_w) for h in hypotheses]
    n = len(labels)
    lc, bc, joint = Counter(labels), Counter(bins), Counter(zip(labels, bins))
    return max(0., sum(count/n * math.log2(count*n / (lc[label]*bc[bin_]))
                       for (label, bin_), count in joint.items()))


class ActiveProbeSupervisor(DynamicProbeSupervisor):
    """Causal supervisor using only the same power/current/voltage/speed inputs.

    Each query returns to the baseline before learning from its A-B-A bracket.
    Only measured candidates can be committed, after a new verification window.
    Historical cost is never erased. No plant truth or future disturbance input.
    Fixed-order and fixed-cost ablations change only that decision mechanism.
    """
    def __init__(self, config: DynamicProbeConfig, active: ActiveProbeConfig,
                 *, active_selection=True, learned_cost=True):
        super().__init__(config)
        if not isinstance(active, ActiveProbeConfig):
            raise TypeError("active must be ActiveProbeConfig")
        if not isinstance(active_selection, bool) or not isinstance(learned_cost, bool):
            raise TypeError("ablations must be boolean")
        self.active = active
        self.active_selection = active_selection
        self.learned_cost = learned_cost
        # Extremes first for the fixed-order ablation; inner probes are symmetric
        # fractions of the available reference interval, not fitted to outcomes.
        self.ids = (config.low_id_a, config.high_id_a,
                    (config.low_id_a + config.baseline_id_a)/2,
                    (config.high_id_a + config.baseline_id_a)/2)
        self.hypotheses = gain_hypotheses(self.ids, config.baseline_id_a)
        self.cycles = []
        self.decisions = []
        self.ever_committed = False
        self.recovery_observed = False
        self.projection_status = "not_evaluated"
        self.projected_net_j = None
        self._query = None
        self._before = None
        self._probe_window = None
        self._intervals = []
        self._return_started = None
        self._query_started = None
        self._cycle_cost_prediction = None
        self._return_prediction_s = None
        self._ever_moved = False
        self._hold_powers = deque()
        self._hold_power = None
        self._hold_speed_ref = None
        self._current_speed_ref = None
        self._regime_speed_ref = None
        self._episode = None
        self.episodes = []

    @property
    def target_id_a(self):
        if self.phase == "query":
            return self.ids[self._query]
        if self.phase in ("candidateverify", "committed"):
            return self.candidate_id_a
        return self.config.baseline_id_a

    def stage_s(self, id_a):
        return (abs(id_a-self.config.baseline_id_a)/self.config.slew_a_per_s
                + self.config.minimum_settle_s + self.config.window_s
                + 2*self.config.dt_s)

    def return_s(self, id_a):
        prediction = self.stage_s(id_a)
        if self.learned_cost and self.cycles:
            prediction = max(prediction, max(c["return_duration_s"] +
                max(0., abs(id_a-self.config.baseline_id_a)-c["amplitude_a"])
                / self.config.slew_a_per_s for c in self.cycles))
        return prediction + self.active.return_margin_s

    def cycle_cost(self, id_a):
        if not self.learned_cost or not self.cycles:
            return self.active.prior_excess_w * 2*self.stage_s(id_a)
        amplitude = abs(id_a-self.config.baseline_id_a)
        # Empirical amplitude transfer, deliberately labelled as a prediction.
        return self.active.cost_floor_j + self.active.cost_multiplier * max(
            c["excess_j"] * max(1., (amplitude/c["amplitude_a"])**2)
            for c in self.cycles)

    @property
    def spent_estimate_j(self):
        return sum(c["excess_j"] for c in self.cycles)

    def _reject(self, time_s, reason, *, abort=True):
        if not self.rejected:
            if self.ever_committed:
                self.projection_status = ("holding_ended_prediction_only" if reason == "scheduled_return"
                                          else "invalidated_by_early_return")
            self.recovery_observed = not self._ever_moved
        elif abort and not self.aborted:
            self.aborted = True
            self.reason = reason
            self._events.append(DynamicProbeEvent(time_s, self.phase, "return_fault", reason))
            if self.ever_committed:
                self.projection_status = "invalidated_by_early_return"
        super()._reject(time_s, reason, abort=abort)

    def _start_episode(self, time_s, kind, predicted_cost):
        self._episode = dict(start_s=time_s, kind=kind, predicted_cost_j=predicted_cost,
                             baseline_before=window_point(self._before), intervals=[], missing_s=0.)

    def _finish_episode(self, window, time_s):
        if self._episode is None:
            return
        episode = self._episode
        after = window_point(window)
        positive = signed = holding_positive = 0.
        phases = Counter()
        for end, dt, power, phase in episode["intervals"]:
            delta = power-interpolated_power(episode["baseline_before"], after, end-dt/2)
            signed += delta*dt
            positive += max(0., delta)*dt
            holding_positive += max(0., delta)*dt if phase == "committed" else 0.
            phases[phase] += 1
        finite = all(math.isfinite(v) for v in (signed, positive, holding_positive))
        self.episodes.append(dict(start_s=episode["start_s"], end_s=time_s,
            kind=episode["kind"], predicted_cost_j=episode["predicted_cost_j"],
            signed_excess_j=signed if finite else None, positive_excess_j=positive if finite else None,
            nonholding_positive_excess_j=positive-holding_positive if finite else None,
            interval_count=len(episode["intervals"]), phases=dict(phases),
            missing_measurement_s=episode["missing_s"],
            interrupted=self.rejected and self.reason != "scheduled_return",
            reason=self.reason, recovery_window_observed=True,
            estimate="retrospective_affine_baseline_not_truth" if finite else "numerical_failure"))
        self._episode = None

    def _decide(self, time_s):
        measured = {c["index"]: c for c in self.cycles}
        options = []
        for index, cycle in measured.items():
            gain = cycle["gain_lower_heuristic_w"]
            remaining = (self.active.hold_until_s-time_s-self.stage_s(self.ids[index])
                         - self.return_s(self.ids[index]))
            net = gain * max(0., remaining)-self.spent_estimate_j-self.cycle_cost(self.ids[index])
            if (gain >= self.config.improvement_margin_w and remaining > 0 and
                    self.spent_estimate_j+self.cycle_cost(self.ids[index]) <= self.active.max_estimated_cost_j):
                options.append((net, index, gain))
        best = max(options, default=None)
        potential = max(0., max(max(h) for h in self.hypotheses))
        resolved = best is not None and best[2]+self.active.decision_regret_w >= potential
        stop = len(self.cycles) >= self.active.max_probes
        remaining = [i for i in range(len(self.ids)) if i not in measured]
        choices = []
        for index in remaining:
            id_a = self.ids[index]
            cost = self.cycle_cost(id_a)
            # Reserve time for the trial, a subsequent verification and return.
            time_needed = 3*self.stage_s(id_a)+self.return_s(id_a)
            possible = (time_s+time_needed < self.active.hold_until_s
                        and self.spent_estimate_j+cost <= self.active.max_estimated_cost_j)
            information = decision_information(self.hypotheses, index,
                                                2*self.active.gain_error_floor_w)
            choices.append(dict(index=index, id_a=id_a, predicted_cost_j=cost,
                                information_bits=information, feasible=possible,
                                score=information/(self.active.cost_floor_j+cost)))
        feasible = [c for c in choices if c["feasible"]]
        self.decisions.append(dict(time_s=time_s, survivors=len(self.hypotheses),
                                   resolved=resolved, choices=choices))
        if best is not None and (resolved or stop or not feasible):
            self.projected_net_j = best[0]
            if (best[0] > self.active.minimum_net_gain_j and
                    self.spent_estimate_j+self.cycle_cost(self.ids[best[1]])
                    <= self.active.max_estimated_cost_j):
                self.candidate_id_a = self.ids[best[1]]
                self._start_episode(time_s, "verification_hold_return", self.cycle_cost(self.candidate_id_a))
                self._enter_stage("candidateverify", time_s)
                return
        if stop or not feasible or resolved:
            self._reject(time_s, "no_profitable_measured_candidate", abort=False)
            return
        chosen = (max(feasible, key=lambda c: (c["score"], -c["index"]))
                  if self.active_selection else feasible[0])
        self.decisions[-1]["selected_index"] = chosen["index"]
        self._query = chosen["index"]
        self._query_started = time_s
        self._cycle_cost_prediction = chosen["predicted_cost_j"]
        self._return_prediction_s = self.return_s(chosen["id_a"])
        self._intervals = []
        self._start_episode(time_s, "query_return", chosen["predicted_cost_j"])
        self._enter_stage("query", time_s)

    def _accept_window(self, window, time_s):
        self._windows.append(window)
        self._events.append(DynamicProbeEvent(time_s, self.phase, "measurement",
                                              measurement=window.measurement))
        if self.phase == "rejected":
            self.recovery_observed = True
            self._finish_episode(window, time_s)
        elif self.phase == "baseline":
            self._before = window
            self._decide(time_s)
        elif self.phase == "query":
            self._probe_window = window
            self._return_started = time_s
            self._enter_stage("return", time_s)
        elif self.phase == "return":
            try:
                result = bracket_estimate(self._before, self._probe_window, window,
                                          self._intervals, self._return_started,
                                          self.active.gain_error_floor_w)
            except ValueError:
                self._reject(time_s, "numerical_failure")
                return
            self._finish_episode(window, time_s)
            result.update(index=self._query, id_a=self.ids[self._query],
                amplitude_a=abs(self.ids[self._query]-self.config.baseline_id_a),
                query_started_s=self._query_started, return_started_s=self._return_started,
                end_s=time_s, return_duration_s=time_s-self._return_started,
                predicted_cost_j=self._cycle_cost_prediction,
                predicted_return_s=self._return_prediction_s)
            self.cycles.append(result)
            self._before = window
            self._intervals = []
            if abs(result["baseline_slope_w_per_s"]) > self.active.max_baseline_slope_w_per_s:
                self._reject(time_s, "baseline_drift", abort=False)
                return
            self.hypotheses = tuple(h for h in self.hypotheses if
                abs(h[self._query]-result["gain_w"]) <= result["error_width_w"])
            if not self.hypotheses:
                self._reject(time_s, "response_hypotheses_falsified", abort=False)
                return
            self._decide(time_s)
        elif self.phase == "candidateverify":
            before_t, before_p = window_point(self._before)
            candidate_t, candidate_p = window_point(window)
            # Only extrapolate the latest *observed* baseline slope, never load truth.
            cycle = self.cycles[-1]
            baseline_prediction = before_p+cycle["baseline_slope_w_per_s"]*(candidate_t-before_t)
            empirical_gain = baseline_prediction-candidate_p
            measured_cycle = next(c for c in self.cycles if c["id_a"] == self.candidate_id_a)
            lower = min(empirical_gain-self.active.gain_error_floor_w-window.power_std_w,
                        measured_cycle["gain_lower_heuristic_w"])
            remaining = self.active.hold_until_s-time_s-self.return_s(self.candidate_id_a)
            self.projected_net_j = (lower*max(0., remaining)-self.spent_estimate_j
                                    - self.cycle_cost(self.candidate_id_a))
            self.improvement_w = empirical_gain
            if (lower >= self.config.improvement_margin_w and remaining > 0
                    and self.projected_net_j > self.active.minimum_net_gain_j):
                self.ever_committed = True
                self.projection_status = "empirical_prediction_not_bound"
                self._hold_power = candidate_p
                self._hold_speed_ref = self._current_speed_ref
                self._enter_stage("committed", time_s)
            else:
                self._reject(time_s, "verification_or_payback_declined", abort=False)

    def step(self, time_s, measured_power_w, measured_current_peak_a,
             measured_voltage_peak_v, measured_speed_rad_s, reference_speed_rad_s,
             voltage_limit_v=None):
        time_s = _finite_real("time_s", time_s)
        if time_s < 0 or (self._last_time_s is not None and time_s <= self._last_time_s):
            raise ValueError("time_s must be nonnegative and strictly increasing")
        elapsed = 0. if self._last_time_s is None else time_s-self._last_time_s
        valid = True
        try:
            p, i, v, speed, ref = [_finite_real("observation", x) for x in (
                measured_power_w, measured_current_peak_a, measured_voltage_peak_v,
                measured_speed_rad_s, reference_speed_rad_s)]
            valid = i >= 0 and v >= 0
            if voltage_limit_v is not None:
                valid &= _finite_real("voltage cap", voltage_limit_v) > 0
        except ValueError:
            valid = False
        gap = elapsed > self.config.dt_s*(1+1e-9)
        self._current_speed_ref = ref if valid else None
        if valid and not gap and self.phase in ("query", "return"):
            self._intervals.append((time_s, elapsed, p))
        if self._episode is not None and valid and not gap:
            self._episode["intervals"].append((time_s, elapsed, p, self.phase))
        elif self._episode is not None:
            self._episode["missing_s"] += elapsed
        if not valid:
            self._reject(time_s, "invalid_measurement")
        elif i > self.config.current_limit_a:
            self._reject(time_s, "current_limit")
        elif v > min(self._voltage_cap_v, voltage_limit_v if voltage_limit_v is not None else self._voltage_cap_v):
            self._reject(time_s, "voltage_limit")
        if valid and time_s >= self.config.start_after_s and self._regime_speed_ref is None:
            self._regime_speed_ref = ref
        if self.phase not in ("waiting", "rejected", "rollback"):
            if gap:
                self._reject(time_s, "sample_gap")
            elif valid and abs(ref-self._regime_speed_ref) > 1e-9:
                self._reject(time_s, "observed_regime_change")
            elif time_s+self.return_s(self.id_ref_a)+2*self.config.dt_s >= self.active.hold_until_s:
                self._reject(time_s, "scheduled_return", abort=False)
            elif valid and self.phase == "committed":
                self._hold_powers.append((time_s, p))
                while self._hold_powers and time_s-self._hold_powers[0][0] > self.config.window_s:
                    self._hold_powers.popleft()
                mean = math.fsum(x[1] for x in self._hold_powers)/len(self._hold_powers)
                if (abs(ref-self._hold_speed_ref) > 1e-9 or
                        abs(speed-ref) > self.config.speed_error_limit_rad_s or
                        abs(mean-self._hold_power) > self.config.repeat_drift_limit_w):
                    self._reject(time_s, "observed_regime_change")
        result = super().step(time_s, measured_power_w, measured_current_peak_a,
                              measured_voltage_peak_v, measured_speed_rad_s,
                              reference_speed_rad_s, voltage_limit_v)
        self._ever_moved |= result.id_ref_a != self.config.baseline_id_a
        if result.phase == "rejected" and not self.recovery_observed:
            if (valid and not gap and i <= self.config.current_limit_a and v <= self._voltage_cap_v):
                self._collect(DynamicProbeSample(time_s, p, i, v), abs(speed-ref))
            else:
                self._reset_window(time_s, "invalid_recovery_observation")
        return replace(result, completed=(self.recovery_observed if self.rejected else
                                           result.completed))

    def summary(self):
        return dict(config=asdict(self.active), active_selection=self.active_selection,
                    learned_cost=self.learned_cost, ids=self.ids,
                    cycles=self.cycles, decisions=self.decisions,
                    hypotheses_remaining=len(self.hypotheses),
                    spent_bracket_estimate_j=self.spent_estimate_j,
                    ever_committed=self.ever_committed, recovery_observed=self.recovery_observed,
                    projected_net_j=self.projected_net_j, projection_status=self.projection_status,
                    episodes=self.episodes,
                    open_episode=(dict(kind=self._episode["kind"], start_s=self._episode["start_s"],
                        predicted_cost_j=self._episode["predicted_cost_j"],
                        known_measured_terminal_j=sum(dt*p for _,dt,p,_ in self._episode["intervals"]),
                        measured_duration_s=sum(dt for _,dt,_,_ in self._episode["intervals"]),
                        missing_measurement_s=self._episode["missing_s"],
                        full_cycle_excess_j=None,
                        interval_count=len(self._episode["intervals"]), recovery_window_observed=False)
                        if self._episode else None),
                    incomplete_cycle_samples=len(self._intervals),
                    certificate="none_empirical_predictor_not_hardware_validated")
