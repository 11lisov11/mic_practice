#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "docs" / "experiments"
PREREGISTRATION = EXPERIMENTS / "AIR56B2_PREREGISTRATION_RU.md"
MATRIX = EXPERIMENTS / "AIR56B2_EXPERIMENT_MATRIX.csv"
LOG_TEMPLATE = EXPERIMENTS / "AIR56B2_EXPERIMENT_LOG_TEMPLATE.csv"


def validate() -> dict[str, object]:
    errors: list[str] = []
    preregistration = PREREGISTRATION.read_text(encoding="utf-8")
    for phrase in (
        "аппаратные результаты отсутствуют",
        "hardware_release_ready",
        "alpha=0,05",
        "мощности не ниже `0,8`",
        "Fault, OOD, fallback",
    ):
        if phrase not in preregistration:
            errors.append(f"preregistration marker missing: {phrase}")

    with MATRIX.open("r", encoding="utf-8", newline="") as handle:
        matrix_rows = list(csv.DictReader(handle))
    expected_points = {(frequency, load) for frequency in (5, 15, 30, 50) for load in (0.25, 0.5, 0.75, 1.0)}
    actual_points = {(int(row["frequency_hz"]), float(row["load_fraction"])) for row in matrix_rows}
    if actual_points != expected_points:
        errors.append("experiment matrix does not contain the exact 4x4 operating grid")
    if any(int(row["minimum_pair_count"]) < 5 for row in matrix_rows):
        errors.append("minimum pair count must be at least five")
    if any(row["status"] != "PLANNED_SENSORLESS_DIAGNOSTIC_ONLY" for row in matrix_rows if row["frequency_hz"] == "5"):
        errors.append("5 Hz sensorless limitation is not fixed in every row")

    with LOG_TEMPLATE.open("r", encoding="utf-8", newline="") as handle:
        log_fields = next(csv.reader(handle))
    required_log_fields = {
        "git_commit",
        "git_tag",
        "nucleo_firmware_sha256",
        "unoq_firmware_sha256",
        "algorithm_config_sha256",
        "dc_input_energy_j",
        "fault_code",
        "raw_log_sha256",
        "exclusion_reason",
    }
    missing = sorted(required_log_fields - set(log_fields))
    if missing:
        errors.append("log template fields missing: " + ", ".join(missing))
    return {
        "schema": "air56b2-experiment-package-validation-v1",
        "status": "PASS" if not errors else "FAIL",
        "hardware_release_ready": False,
        "matrix_row_count": len(matrix_rows),
        "log_field_count": len(log_fields),
        "errors": errors,
    }


def main() -> int:
    result = validate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
