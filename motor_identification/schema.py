from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence


CAPTURE_SCHEMA = "mic_ai.motor_identification.capture.v1"
PRIOR_SCHEMA = "mic_ai.motor_identification.prior.v1"
RESULT_SCHEMA = "mic_ai.motor_identification.result.v1"

SAMPLE_FIELDS = (
    "t_s",
    "v_alpha_v",
    "v_beta_v",
    "i_alpha_a",
    "i_beta_a",
    "omega_rad_s",
)
ABC_SAMPLE_FIELDS = (
    "t_s",
    "v_a_v",
    "v_b_v",
    "v_c_v",
    "i_a_a",
    "i_b_a",
    "i_c_a",
)
EXPERIMENT_KINDS = {"standstill", "free_run", "coast"}
EXPERIMENT_ROLES = {"fit", "validation"}
VOLTAGE_SOURCES = {"measured_alpha_beta", "calibrated_pwm_reconstruction"}


@dataclass(frozen=True)
class ContractIssue:
    severity: str
    code: str
    path: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "path": self.path,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ContractReport:
    issues: tuple[ContractIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def as_dict(self) -> dict[str, Any]:
        errors = [issue.as_dict() for issue in self.issues if issue.severity == "error"]
        warnings = [issue.as_dict() for issue in self.issues if issue.severity == "warning"]
        return {
            "pass": self.passed,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings,
        }


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _float_list(values: Iterable[object], *, field: str) -> list[float]:
    result: list[float] = []
    for index, value in enumerate(values):
        try:
            result.append(float(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field}[{index}] must be numeric") from exc
    return result


def _abc_to_alpha_beta(a: float, b: float, c: float) -> tuple[float, float]:
    return (
        (2.0 / 3.0) * (a - 0.5 * b - 0.5 * c),
        (2.0 / 3.0) * (math.sqrt(3.0) * 0.5 * (b - c)),
    )


def _read_samples_csv(path: Path) -> dict[str, list[float]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or ())
        alpha_beta = set(SAMPLE_FIELDS).issubset(headers)
        abc = set(ABC_SAMPLE_FIELDS).issubset(headers) and (
            "omega_rad_s" in headers or "omega_rpm" in headers
        )
        if not alpha_beta and not abc:
            raise ValueError(
                f"{path}: CSV must contain alpha-beta columns {SAMPLE_FIELDS} or ABC columns "
                f"{ABC_SAMPLE_FIELDS} plus omega_rad_s/omega_rpm"
            )

        samples = {field: [] for field in SAMPLE_FIELDS}
        current_sum_samples: list[float] = []
        phase_current_peak = 0.0
        for row_index, row in enumerate(reader, start=2):
            try:
                if alpha_beta:
                    for field in SAMPLE_FIELDS:
                        samples[field].append(float(row[field]))
                else:
                    va, vb = _abc_to_alpha_beta(
                        float(row["v_a_v"]), float(row["v_b_v"]), float(row["v_c_v"])
                    )
                    ia, ib = _abc_to_alpha_beta(
                        float(row["i_a_a"]), float(row["i_b_a"]), float(row["i_c_a"])
                    )
                    phase_currents = (
                        float(row["i_a_a"]),
                        float(row["i_b_a"]),
                        float(row["i_c_a"]),
                    )
                    current_sum_samples.append(sum(phase_currents))
                    phase_current_peak = max(phase_current_peak, *(abs(value) for value in phase_currents))
                    omega = (
                        float(row["omega_rad_s"])
                        if "omega_rad_s" in headers
                        else float(row["omega_rpm"]) * 2.0 * math.pi / 60.0
                    )
                    samples["t_s"].append(float(row["t_s"]))
                    samples["v_alpha_v"].append(va)
                    samples["v_beta_v"].append(vb)
                    samples["i_alpha_a"].append(ia)
                    samples["i_beta_a"].append(ib)
                    samples["omega_rad_s"].append(omega)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"{path}: invalid numeric value at CSV row {row_index}") from exc
        if abc and current_sum_samples:
            imbalance_rms = math.sqrt(
                sum(value * value for value in current_sum_samples) / len(current_sum_samples)
            )
            imbalance_limit = max(0.02, 0.05 * phase_current_peak)
            if imbalance_rms > imbalance_limit:
                raise ValueError(
                    f"{path}: three-phase current sum RMS {imbalance_rms:.6g} A exceeds "
                    f"{imbalance_limit:.6g} A; check offsets, units, and channel mapping"
                )
    return samples


def _expand_csv_experiments(payload: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    root = manifest_path.resolve().parent
    experiments = payload.get("experiments")
    if not isinstance(experiments, list):
        return payload
    expanded: list[Any] = []
    for item in experiments:
        if not isinstance(item, dict) or "samples_csv" not in item:
            expanded.append(item)
            continue
        relative = Path(str(item["samples_csv"]))
        csv_path = (root / relative).resolve()
        try:
            csv_path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"samples_csv escapes manifest directory: {relative}") from exc
        replacement = dict(item)
        replacement.pop("samples_csv", None)
        replacement["samples"] = _read_samples_csv(csv_path)
        expanded.append(replacement)
    result = dict(payload)
    result["experiments"] = expanded
    return result


def load_capture(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if source.is_dir():
        source = source / "capture.json"
    if source.suffix.lower() != ".json":
        raise ValueError("capture input must be a JSON manifest or a directory containing capture.json")
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("capture root must be a JSON object")
    return _expand_csv_experiments(payload, source)


def load_prior(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("prior root must be a JSON object")
    return payload


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_capture(payload: Mapping[str, Any]) -> ContractReport:
    issues: list[ContractIssue] = []

    def issue(severity: str, code: str, path: str, detail: str) -> None:
        issues.append(ContractIssue(severity, code, path, detail))

    if payload.get("schema") != CAPTURE_SCHEMA:
        issue("error", "schema", "schema", f"expected {CAPTURE_SCHEMA}")
    if not _nonempty_string(payload.get("motor_id")):
        issue("error", "motor_id", "motor_id", "motor_id must be a non-empty string")

    source = payload.get("source")
    source_kind = source.get("kind") if isinstance(source, Mapping) else None
    if source_kind not in {"hardware", "synthetic"}:
        issue("error", "source_kind", "source.kind", "source.kind must be hardware or synthetic")
    if source_kind == "hardware":
        for field in ("device_id", "firmware_sha256", "clock", "capture_software"):
            if not isinstance(source, Mapping) or not _nonempty_string(source.get(field)):
                issue("error", "hardware_provenance", f"source.{field}", f"hardware source requires {field}")
        firmware_hash = str(source.get("firmware_sha256", "")) if isinstance(source, Mapping) else ""
        if firmware_hash and re.fullmatch(r"[0-9a-fA-F]{64}", firmware_hash) is None:
            issue(
                "error",
                "firmware_hash",
                "source.firmware_sha256",
                "firmware_sha256 must contain exactly 64 hexadecimal characters",
            )
        calibration = source.get("calibration") if isinstance(source, Mapping) else None
        for field in ("current", "voltage", "speed"):
            if not isinstance(calibration, Mapping) or not _nonempty_string(calibration.get(field)):
                issue(
                    "error",
                    "calibration_provenance",
                    f"source.calibration.{field}",
                    f"hardware source requires a traceable {field} calibration id",
                )
        if "true_params" in payload:
            issue("error", "truth_leakage", "true_params", "hardware capture must not contain true_params")

    noise = payload.get("noise_std")
    for field in ("i_alpha_a", "i_beta_a", "omega_rad_s"):
        try:
            value = float(noise[field]) if isinstance(noise, Mapping) else math.nan
        except (KeyError, TypeError, ValueError):
            value = math.nan
        if not math.isfinite(value) or value <= 0.0:
            issue("error", "noise_std", f"noise_std.{field}", "noise standard deviation must be finite and positive")

    limits = payload.get("limits") if isinstance(payload.get("limits"), Mapping) else {}
    try:
        max_voltage = float(limits.get("max_abs_voltage_v", 500.0))
        max_current = float(limits.get("max_abs_current_a", 100.0))
        max_speed = float(limits.get("max_abs_speed_rad_s", 2000.0))
    except (TypeError, ValueError):
        max_voltage, max_current, max_speed = 500.0, 100.0, 2000.0
        issue("error", "limits", "limits", "limits must be numeric")

    experiments = payload.get("experiments")
    if not isinstance(experiments, Sequence) or isinstance(experiments, (str, bytes)):
        issue("error", "experiments", "experiments", "experiments must be an array")
        return ContractReport(tuple(issues))

    seen_ids: set[str] = set()
    run_ids = {"fit": set(), "validation": set()}
    coverage = {"fit": set(), "validation": set()}
    sample_signatures = {"fit": set(), "validation": set()}
    dynamic_load_conditions: set[str] = set()
    hardware_temperatures: list[float] = []
    for index, experiment in enumerate(experiments):
        path = f"experiments[{index}]"
        if not isinstance(experiment, Mapping):
            issue("error", "experiment_type", path, "experiment must be an object")
            continue
        experiment_id = experiment.get("id")
        if not _nonempty_string(experiment_id):
            issue("error", "experiment_id", f"{path}.id", "id must be a non-empty string")
        elif str(experiment_id) in seen_ids:
            issue("error", "duplicate_experiment", f"{path}.id", "experiment id must be unique")
        else:
            seen_ids.add(str(experiment_id))

        role = experiment.get("role")
        kind = experiment.get("kind")
        if role not in EXPERIMENT_ROLES:
            issue("error", "experiment_role", f"{path}.role", "role must be fit or validation")
        if kind not in EXPERIMENT_KINDS:
            issue("error", "experiment_kind", f"{path}.kind", "kind must be standstill, free_run, or coast")
        if role in EXPERIMENT_ROLES and kind in EXPERIMENT_KINDS:
            coverage[str(role)].add(str(kind))
        if source_kind == "hardware" and not _nonempty_string(experiment.get("captured_utc")):
            issue(
                "error",
                "capture_timestamp",
                f"{path}.captured_utc",
                "hardware experiment requires an independent capture timestamp",
            )
        elif source_kind == "hardware":
            try:
                captured_at = datetime.fromisoformat(str(experiment["captured_utc"]).replace("Z", "+00:00"))
                if captured_at.tzinfo is None:
                    raise ValueError("timezone missing")
            except (KeyError, TypeError, ValueError):
                issue(
                    "error",
                    "capture_timestamp_format",
                    f"{path}.captured_utc",
                    "captured_utc must be an ISO-8601 timestamp with timezone",
                )
        if source_kind == "hardware":
            load_condition = experiment.get("load_condition_id")
            if not _nonempty_string(load_condition):
                issue(
                    "error",
                    "load_condition",
                    f"{path}.load_condition_id",
                    "hardware experiment requires a traceable load_condition_id",
                )
            elif kind != "standstill":
                dynamic_load_conditions.add(str(load_condition).strip())
            try:
                temperature = float(experiment.get("motor_temperature_c", math.nan))
            except (TypeError, ValueError):
                temperature = math.nan
            if not math.isfinite(temperature) or not -40.0 <= temperature <= 200.0:
                issue(
                    "error",
                    "motor_temperature",
                    f"{path}.motor_temperature_c",
                    "hardware experiment requires motor_temperature_c within -40..200 C",
                )
            else:
                hardware_temperatures.append(temperature)

        run_id = experiment.get("run_id")
        if not _nonempty_string(run_id):
            issue("error", "run_id", f"{path}.run_id", "run_id is required for independent validation")
        elif role in EXPERIMENT_ROLES:
            run_ids[str(role)].add(str(run_id))

        rotor_locked = experiment.get("rotor_locked")
        if not isinstance(rotor_locked, bool):
            issue("error", "rotor_locked", f"{path}.rotor_locked", "rotor_locked must be boolean")
        if kind == "standstill" and rotor_locked is not True:
            issue("error", "standstill_lock", f"{path}.rotor_locked", "standstill experiment requires a physical rotor lock")
        if kind != "standstill" and rotor_locked is True:
            issue("error", "unexpected_lock", f"{path}.rotor_locked", f"{kind} experiment must not be rotor locked")
        if experiment.get("initial_state") != "deenergized":
            issue(
                "error",
                "initial_state",
                f"{path}.initial_state",
                "only deenergized initial state is supported; demagnetize before every experiment",
            )
        try:
            initial_omega = float(experiment.get("initial_omega_rad_s", math.nan))
        except (TypeError, ValueError):
            initial_omega = math.nan
        if not math.isfinite(initial_omega):
            issue(
                "error",
                "initial_omega",
                f"{path}.initial_omega_rad_s",
                "initial_omega_rad_s must be finite and explicitly recorded",
            )
        elif rotor_locked is True and abs(initial_omega) > 1.0:
            issue(
                "error",
                "initial_omega_lock",
                f"{path}.initial_omega_rad_s",
                "rotor-locked experiment must start near zero speed",
            )
        elif kind == "coast" and abs(initial_omega) < 1.0:
            issue(
                "error",
                "coast_initial_speed",
                f"{path}.initial_omega_rad_s",
                "coast experiment must start above 1 rad/s",
            )
        if experiment.get("voltage_source") not in VOLTAGE_SOURCES:
            issue(
                "error",
                "voltage_source",
                f"{path}.voltage_source",
                f"voltage_source must be one of {sorted(VOLTAGE_SOURCES)}",
            )

        samples = experiment.get("samples")
        if not isinstance(samples, Mapping):
            issue("error", "samples", f"{path}.samples", "samples object is required")
            continue
        numeric: dict[str, list[float]] = {}
        for field in SAMPLE_FIELDS:
            values = samples.get(field)
            if not _is_sequence(values):
                issue("error", "sample_field", f"{path}.samples.{field}", "sample field must be an array")
                continue
            try:
                numeric[field] = _float_list(values, field=f"{path}.samples.{field}")
            except ValueError as exc:
                issue("error", "sample_numeric", f"{path}.samples.{field}", str(exc))
        if len(numeric) != len(SAMPLE_FIELDS):
            continue
        lengths = {len(values) for values in numeric.values()}
        if len(lengths) != 1:
            issue("error", "sample_lengths", f"{path}.samples", "all sample arrays must have equal length")
            continue
        sample_count = next(iter(lengths), 0)
        if sample_count < 64:
            issue("error", "sample_count", f"{path}.samples", "at least 64 samples are required")
            continue
        if not all(math.isfinite(value) for values in numeric.values() for value in values):
            issue("error", "non_finite", f"{path}.samples", "samples contain NaN or infinity")
            continue

        if role in EXPERIMENT_ROLES:
            digest = hashlib.sha256()
            for field in SAMPLE_FIELDS:
                digest.update(field.encode("ascii"))
                digest.update(json.dumps(numeric[field], separators=(",", ":")).encode("ascii"))
            sample_signatures[str(role)].add(digest.hexdigest())

        times = numeric["t_s"]
        deltas = [right - left for left, right in zip(times, times[1:])]
        if any(delta <= 0.0 for delta in deltas):
            issue("error", "time_order", f"{path}.samples.t_s", "timestamps must be strictly increasing")
        else:
            dt = median(deltas)
            jitter = max(abs(delta - dt) for delta in deltas) / max(dt, 1.0e-15)
            if jitter > 0.05:
                issue("error", "sample_jitter", f"{path}.samples.t_s", f"sample-period jitter {jitter:.3f} exceeds 5%")
            max_dt = 0.02 if kind == "coast" else 0.002
            if dt > max_dt:
                issue("error", "sample_rate", f"{path}.samples.t_s", f"median dt={dt:.6g}s exceeds {max_dt:.6g}s for {kind}")

        voltage_peak = max(
            math.hypot(alpha, beta)
            for alpha, beta in zip(numeric["v_alpha_v"], numeric["v_beta_v"])
        )
        current_peak = max(
            math.hypot(alpha, beta)
            for alpha, beta in zip(numeric["i_alpha_a"], numeric["i_beta_a"])
        )
        if voltage_peak > max_voltage:
            issue("error", "voltage_limit", f"{path}.samples", "voltage exceeds declared capture limit")
        if current_peak > max_current:
            issue("error", "current_limit", f"{path}.samples", "current exceeds declared capture limit")
        if max(abs(value) for value in numeric["omega_rad_s"]) > max_speed:
            issue("error", "speed_limit", f"{path}.samples.omega_rad_s", "speed exceeds declared capture limit")
        if rotor_locked is True and max(abs(value) for value in numeric["omega_rad_s"]) > 1.0:
            issue("error", "lock_motion", f"{path}.samples.omega_rad_s", "rotor-locked speed exceeds 1 rad/s")
        if kind == "coast" and voltage_peak > 0.5:
            issue("error", "coast_voltage", f"{path}.samples", "coast experiment must have near-zero applied voltage")

    required_coverage = {"standstill", "free_run", "coast"}
    for role in ("fit", "validation"):
        missing = sorted(required_coverage - coverage[role])
        if missing:
            issue("error", "coverage", "experiments", f"{role} set is missing experiments: {', '.join(missing)}")
    overlap = sorted(run_ids["fit"] & run_ids["validation"])
    if overlap:
        issue("error", "validation_leakage", "experiments", f"fit and validation reuse run_id values: {overlap}")
    duplicate_samples = sorted(sample_signatures["fit"] & sample_signatures["validation"])
    if duplicate_samples:
        issue(
            "error",
            "validation_data_reuse",
            "experiments",
            "fit and validation contain byte-equivalent normalized sample arrays",
        )
    if source_kind == "hardware" and len(dynamic_load_conditions) != 1:
        issue(
            "error",
            "load_condition_mismatch",
            "experiments",
            "all hardware free_run/coast fit and validation experiments must use one load_condition_id",
        )
    if source_kind == "hardware" and hardware_temperatures:
        temperature_span = max(hardware_temperatures) - min(hardware_temperatures)
        if temperature_span > 5.0:
            issue(
                "error",
                "temperature_span",
                "experiments",
                f"motor temperature span {temperature_span:.3f} C exceeds 5 C",
            )

    if math.isfinite(max_current) and max_current > 0.0 and isinstance(noise, Mapping):
        for field in ("i_alpha_a", "i_beta_a"):
            try:
                noise_value = float(noise[field])
            except (KeyError, TypeError, ValueError):
                continue
            if noise_value > 0.1 * max_current:
                issue(
                    "error",
                    "noise_scale_implausible",
                    f"noise_std.{field}",
                    "current noise exceeds 10% of declared capture current range",
                )
    if math.isfinite(max_speed) and max_speed > 0.0 and isinstance(noise, Mapping):
        try:
            speed_noise = float(noise["omega_rad_s"])
        except (KeyError, TypeError, ValueError):
            speed_noise = 0.0
        if speed_noise > 0.1 * max_speed:
            issue(
                "error",
                "noise_scale_implausible",
                "noise_std.omega_rad_s",
                "speed noise exceeds 10% of declared capture speed range",
            )
    return ContractReport(tuple(issues))


def normalized_samples(experiment: Mapping[str, Any]) -> dict[str, list[float]]:
    samples = experiment["samples"]
    return {field: _float_list(samples[field], field=field) for field in SAMPLE_FIELDS}


__all__ = [
    "ABC_SAMPLE_FIELDS",
    "CAPTURE_SCHEMA",
    "ContractIssue",
    "ContractReport",
    "PRIOR_SCHEMA",
    "RESULT_SCHEMA",
    "SAMPLE_FIELDS",
    "load_capture",
    "load_prior",
    "normalized_samples",
    "validate_capture",
]
