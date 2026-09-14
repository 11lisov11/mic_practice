"""One-shot settled electrical probing, without access to a plant or loss oracle.

Samples passed to ``step`` must precede application of its returned reference.
Settling means the *command* has stopped slewing, measured speed tracks its
reference, and measured power is stable. There is no measured d-axis current
input, so this cannot certify physical current/flux settling. Likewise, reacting
to observed electrical risk does not prevent instantaneous limit violations;
independent fast current/voltage protection remains necessary.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, fields
import math
from numbers import Real

from control.air56b2_measured_loss_fit import (
    MeasuredLossFitConfig,
    MeasuredLossFitResult,
    ProbeMeasurement,
    fit_measured_loss_reference,
)


def _finite_real(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        value = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite real number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return value


@dataclass(frozen=True)
class DynamicProbeConfig:
    dt_s: float
    baseline_id_a: float = 0.83
    low_id_a: float = 0.65
    high_id_a: float = 1.0
    slew_a_per_s: float = 1.5
    start_after_s: float = 0.8
    minimum_settle_s: float = 0.15
    window_s: float = 0.12
    max_stage_s: float = 1.2
    speed_error_limit_rad_s: float = 3.0
    power_cv_tolerance: float = 0.03
    power_abs_tolerance_w: float = 2.0
    current_limit_a: float = 3.1
    voltage_limit_v: float = 170.0
    repeat_drift_limit_w: float = 4.0
    improvement_margin_w: float = 2.0

    def __post_init__(self) -> None:
        for field in fields(self):
            object.__setattr__(
                self, field.name, _finite_real(field.name, getattr(self, field.name))
            )
        for name in (
            "dt_s",
            "slew_a_per_s",
            "window_s",
            "max_stage_s",
            "current_limit_a",
            "voltage_limit_v",
        ):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be positive")
        for name in (
            "start_after_s",
            "minimum_settle_s",
            "speed_error_limit_rad_s",
            "power_cv_tolerance",
            "power_abs_tolerance_w",
            "repeat_drift_limit_w",
            "improvement_margin_w",
        ):
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} must be nonnegative")
        if not 0.0 < self.low_id_a < self.baseline_id_a < self.high_id_a:
            raise ValueError("IDs must satisfy 0 < low < baseline < high")


@dataclass(frozen=True)
class DynamicProbeSample:
    time_s: float
    power_w: float
    current_peak_a: float
    voltage_peak_v: float


@dataclass(frozen=True)
class SettledProbeWindow:
    phase: str
    samples: tuple[DynamicProbeSample, ...]
    measurement: ProbeMeasurement
    power_std_w: float
    power_half_drift_w: float
    power_endpoint_drift_w: float
    power_tolerance_w: float


@dataclass(frozen=True)
class DynamicProbeEvent:
    time_s: float
    phase: str
    kind: str
    reason: str | None = None
    measurement: ProbeMeasurement | None = None


@dataclass(frozen=True)
class DynamicProbeOutput:
    time_s: float
    id_ref_a: float
    target_id_a: float
    phase: str
    completed: bool
    committed: bool
    rejected: bool
    aborted: bool
    reason: str | None
    candidate_id_a: float | None
    improvement_w: float | None


ProbeSelector = Callable[
    [tuple[ProbeMeasurement, ProbeMeasurement, ProbeMeasurement]],
    float | ProbeMeasurement | MeasuredLossFitResult | None,
]


def _mean(values: tuple[float, ...]) -> float:
    # Dividing first also permits a large, finite common power offset.
    return math.fsum(value / len(values) for value in values)


class DynamicProbeSupervisor:
    """baseline -> low -> high -> baseline_repeat -> candidateverify.

    ``selector`` receives exactly three time-averaged ProbeMeasurements in
    baseline/low/high order. The baseline averages the two baseline windows.
    It returns an ID, a ProbeMeasurement, a MeasuredLossFitResult, or None to
    decline. None *as the callback* uses the existing analytic fitter, including
    its measured fallback. A best-probe callback can return ``min(probes,
    key=lambda p: (p.power_w, p.id_a))``. Every proposal must pass the same
    observed limits, repeat drift, fresh settling, and improvement checks.

    ``dt_s`` is the maximum expected sample interval. A gap restarts settling;
    reference movement is capped at slew * min(elapsed, dt_s), including on
    rollback. Windows contain at least four samples spanning ``window_s`` after
    ``minimum_settle_s``. Stage deadlines include slewing and never reset.
    ``start_after_s`` is an absolute time on the caller's nonnegative clock.

    Electrical limits use strict exceedance, consistent with the fitter. An
    optional positive observed voltage cap can only tighten the configured cap;
    the smallest cap seen is retained for the experiment. Rejection is latched,
    whereas ``completed`` waits for rollback to reach baseline. A committed
    output holds its candidate but still rolls back on later electrical risk
    or invalid observations. New experiments require a new supervisor.
    """

    def __init__(
        self, config: DynamicProbeConfig, selector: ProbeSelector | None = None
    ) -> None:
        if not isinstance(config, DynamicProbeConfig):
            raise TypeError("config must be a DynamicProbeConfig")
        if selector is not None and not callable(selector):
            raise TypeError("selector must be callable or None")
        self.config = config
        self.selector = selector
        self.id_ref_a = config.baseline_id_a
        self.phase = "waiting"
        self.candidate_id_a: float | None = None
        self.improvement_w: float | None = None
        self.fit_result: MeasuredLossFitResult | None = None
        self.rejected = False
        self.aborted = False
        self.reason: str | None = None
        self._last_time_s: float | None = None
        self._stage_started_s = 0.0
        self._settled_since_s: float | None = None
        self._voltage_cap_v = config.voltage_limit_v
        self._pending: deque[DynamicProbeSample] = deque()
        self._windows: list[SettledProbeWindow] = []
        self._events: list[DynamicProbeEvent] = []

    @property
    def events(self) -> tuple[dict[str, object], ...]:
        """JSON-serializable event snapshots, including nested measurements."""
        return tuple(asdict(event) for event in self._events)

    @property
    def windows(self) -> tuple[SettledProbeWindow, ...]:
        return tuple(self._windows)

    @property
    def window_samples(self) -> tuple[DynamicProbeSample, ...]:
        """Current, not-yet-accepted window; an immutable snapshot."""
        return tuple(self._pending)

    @property
    def measurements(self) -> dict[str, ProbeMeasurement]:
        """Accepted stage averages; changing this copy cannot change the run."""
        return {window.phase: window.measurement for window in self._windows}

    @property
    def target_id_a(self) -> float:
        if self.phase == "low":
            return self.config.low_id_a
        if self.phase == "high":
            return self.config.high_id_a
        if self.phase in ("candidateverify", "committed"):
            assert self.candidate_id_a is not None
            return self.candidate_id_a
        return self.config.baseline_id_a

    def _reset_window(self, time_s: float, reason: str) -> None:
        if self._settled_since_s is not None or self._pending:
            self._events.append(
                DynamicProbeEvent(time_s, self.phase, "window_reset", reason)
            )
        self._settled_since_s = None
        self._pending.clear()

    def _enter_stage(self, phase: str, time_s: float) -> None:
        self.phase = phase
        self._stage_started_s = time_s
        self._settled_since_s = None
        self._pending.clear()
        self._events.append(DynamicProbeEvent(time_s, phase, "stage_started"))

    def _reject(self, time_s: float, reason: str, *, abort: bool = True) -> None:
        if self.rejected:
            return
        self.rejected = True
        self.aborted = abort
        self.reason = reason
        self._events.append(DynamicProbeEvent(time_s, self.phase, "rejected", reason))
        self._enter_stage("rollback", time_s)

    def _select_candidate(self, time_s: float) -> None:
        measured = self.measurements
        first, repeat = measured["baseline"], measured["baseline_repeat"]
        if abs(first.power_w - repeat.power_w) > self.config.repeat_drift_limit_w:
            self._reject(time_s, "baseline_repeat_drift")
            return
        baseline = ProbeMeasurement(
            self.config.baseline_id_a,
            _mean((first.power_w, repeat.power_w)),
            _mean((first.current_peak_a, repeat.current_peak_a)),
            _mean((first.voltage_peak_v, repeat.voltage_peak_v)),
        )
        probes = (baseline, measured["low"], measured["high"])
        # A later cap reduction must not make older, infeasible probes usable.
        if any(
            sample.current_peak_a > self.config.current_limit_a
            or sample.voltage_peak_v > self._voltage_cap_v
            for window in self._windows
            for sample in window.samples
        ):
            self._reject(time_s, "probe_limits")
            return
        try:
            if self.selector is None:
                selected = fit_measured_loss_reference(
                    probes,
                    MeasuredLossFitConfig(
                        self.config.low_id_a,
                        self.config.high_id_a,
                        self.config.current_limit_a,
                        self._voltage_cap_v,
                    ),
                )
            else:
                selected = self.selector(probes)
        except Exception:
            self._reject(time_s, "selector_failed")
            return
        if isinstance(selected, MeasuredLossFitResult):
            self.fit_result = selected
            self._events.append(
                DynamicProbeEvent(time_s, self.phase, "selection", selected.reason)
            )
            selected = selected.id_a
        elif isinstance(selected, ProbeMeasurement):
            selected = selected.id_a
        if selected is None:
            self._reject(time_s, "no_candidate", abort=False)
            return
        try:
            candidate = _finite_real("candidate_id_a", selected)
        except ValueError:
            self._reject(time_s, "invalid_candidate")
            return
        if not self.config.low_id_a <= candidate <= self.config.high_id_a:
            self._reject(time_s, "candidate_out_of_bounds")
            return
        self.candidate_id_a = candidate
        self._enter_stage("candidateverify", time_s)

    def _accept_window(self, window: SettledProbeWindow, time_s: float) -> None:
        self._windows.append(window)
        self._events.append(
            DynamicProbeEvent(
                time_s, self.phase, "measurement", measurement=window.measurement
            )
        )
        if self.phase == "baseline_repeat":
            self._select_candidate(time_s)
        elif self.phase == "candidateverify":
            measured = self.measurements
            # Improvement must hold against BOTH baseline observations.
            self.improvement_w = (
                min(measured["baseline"].power_w, measured["baseline_repeat"].power_w)
                - window.measurement.power_w
            )
            if not math.isfinite(self.improvement_w):
                self._reject(time_s, "numerical_failure")
            elif self.improvement_w > 0.0 and (
                self.improvement_w >= self.config.improvement_margin_w
            ):
                self._enter_stage("committed", time_s)
            else:
                self._reject(time_s, "insufficient_improvement", abort=False)
        else:
            following = {"baseline": "low", "low": "high", "high": "baseline_repeat"}
            self._enter_stage(following[self.phase], time_s)

    def _collect(self, sample: DynamicProbeSample, speed_error: float) -> None:
        config, time_s = self.config, sample.time_s
        if self.id_ref_a != self.target_id_a:
            self._reset_window(time_s, "id_unsettled")
            return
        if speed_error > config.speed_error_limit_rad_s:
            self._reset_window(time_s, "speed_error")
            return
        if self._settled_since_s is None:
            self._settled_since_s = time_s
        if (
            time_s - self._settled_since_s + config.dt_s * 1e-9
            < config.minimum_settle_s
        ):
            return
        self._pending.append(sample)
        while len(self._pending) > 4 and (
            time_s - self._pending[1].time_s + config.dt_s * 1e-9 >= config.window_s
        ):
            self._pending.popleft()
        if len(self._pending) < 4 or (
            time_s - self._pending[0].time_s + config.dt_s * 1e-9 < config.window_s
        ):
            return
        samples = tuple(self._pending)
        powers = tuple(item.power_w for item in samples)
        mean = _mean(powers)
        scale = max(abs(power) for power in powers) or 1.0
        std = scale * math.sqrt(
            _mean(tuple((p / scale - mean / scale) ** 2 for p in powers))
        )
        half, edge = len(powers) // 2, max(1, len(powers) // 4)
        half_drift = abs(_mean(powers[:half]) - _mean(powers[-half:]))
        endpoint_drift = abs(_mean(powers[:edge]) - _mean(powers[-edge:]))
        tolerance = config.power_abs_tolerance_w + config.power_cv_tolerance * abs(mean)
        if not all(
            math.isfinite(value)
            for value in (mean, std, half_drift, endpoint_drift, tolerance)
        ):
            self._reject(time_s, "numerical_failure")
            return
        if max(std, half_drift, endpoint_drift) > tolerance:
            return
        measurement = ProbeMeasurement(
            self.target_id_a,
            mean,
            _mean(tuple(item.current_peak_a for item in samples)),
            _mean(tuple(item.voltage_peak_v for item in samples)),
        )
        self._accept_window(
            SettledProbeWindow(
                self.phase,
                samples,
                measurement,
                std,
                half_drift,
                endpoint_drift,
                tolerance,
            ),
            time_s,
        )

    def step(
        self,
        time_s: float,
        measured_power_w: float,
        measured_current_peak_a: float,
        measured_voltage_peak_v: float,
        measured_speed_rad_s: float,
        reference_speed_rad_s: float,
        voltage_limit_v: float | None = None,
    ) -> DynamicProbeOutput:
        """Consume one observation, then issue a slew-limited command.

        Invalid/non-increasing timestamps raise ValueError without changing
        state. Invalid observation values latch ``invalid_measurement`` and
        roll back; finite negative power/speed are allowed, negative peaks are
        not. The first call starts from the configured baseline reference.
        """
        time_s = _finite_real("time_s", time_s)
        if time_s < 0.0 or (
            self._last_time_s is not None and time_s <= self._last_time_s
        ):
            raise ValueError("time_s must be nonnegative and strictly increasing")
        elapsed = 0.0 if self._last_time_s is None else time_s - self._last_time_s
        self._last_time_s = time_s
        sample = None
        speed_error = math.inf
        try:
            sample = DynamicProbeSample(
                time_s,
                _finite_real("measured_power_w", measured_power_w),
                _finite_real("measured_current_peak_a", measured_current_peak_a),
                _finite_real("measured_voltage_peak_v", measured_voltage_peak_v),
            )
            speed_error = abs(
                _finite_real("measured_speed_rad_s", measured_speed_rad_s)
                - _finite_real("reference_speed_rad_s", reference_speed_rad_s)
            )
            if sample.current_peak_a < 0.0 or sample.voltage_peak_v < 0.0:
                raise ValueError("measured peaks must be nonnegative")
            if voltage_limit_v is not None:
                voltage_limit_v = _finite_real("voltage_limit_v", voltage_limit_v)
                if voltage_limit_v <= 0.0:
                    raise ValueError("observed voltage cap must be positive")
                self._voltage_cap_v = min(self._voltage_cap_v, voltage_limit_v)
        except ValueError:
            self._reject(time_s, "invalid_measurement")
        else:
            if sample.current_peak_a > self.config.current_limit_a:
                self._reject(time_s, "current_limit")
            elif sample.voltage_peak_v > self._voltage_cap_v:
                self._reject(time_s, "voltage_limit")

        if self.phase == "waiting" and time_s >= self.config.start_after_s:
            self._enter_stage("baseline", time_s)
        if self.phase not in ("waiting", "rollback", "rejected", "committed"):
            if (
                time_s - self._stage_started_s
                > self.config.max_stage_s + self.config.dt_s * 1e-9
            ):
                self._reject(time_s, f"stage_timeout:{self.phase}")
            else:
                if elapsed > self.config.dt_s * (1.0 + 1e-9):
                    self._reset_window(time_s, "sample_gap")
                assert sample is not None
                self._collect(sample, speed_error)
                if self.phase not in ("rollback", "rejected", "committed") and (
                    time_s - self._stage_started_s + self.config.dt_s * 1e-9
                    >= self.config.max_stage_s
                ):
                    self._reject(time_s, f"stage_timeout:{self.phase}")

        target = self.target_id_a
        movement = self.config.slew_a_per_s * min(elapsed, self.config.dt_s)
        difference = target - self.id_ref_a
        if abs(difference) <= movement:
            self.id_ref_a = target
        else:
            self.id_ref_a += math.copysign(movement, difference)
        if self.phase == "rollback" and self.id_ref_a == self.config.baseline_id_a:
            self._enter_stage("rejected", time_s)
        return DynamicProbeOutput(
            time_s,
            self.id_ref_a,
            self.target_id_a,
            self.phase,
            self.phase in ("committed", "rejected"),
            self.phase == "committed",
            self.rejected,
            self.aborted,
            self.reason,
            self.candidate_id_a,
            self.improvement_w,
        )
