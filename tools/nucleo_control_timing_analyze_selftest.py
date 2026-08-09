#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from nucleo_control_timing_analyze import analyze_marker


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""


def write_capture(
    path: Path,
    *,
    pulse_count: int = 200,
    execution_us: float = 4.0,
    skip_index: int | None = None,
    jitter_us: float = 0.0,
) -> None:
    rows: list[tuple[float, int]] = [(0.0, 1)]
    for index in range(pulse_count):
        if index == skip_index:
            continue
        start_us = 10.0 + 50.0 * index
        if jitter_us and index % 2:
            start_us += jitter_us
        rows.append((start_us * 1e-6, 0))
        rows.append(((start_us + execution_us) * 1e-6, 1))
    rows.append(((10.0 + 50.0 * pulse_count) * 1e-6, 1))
    rows.sort(key=lambda item: item[0])
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Time [s]", "Channel 7"])
        for timestamp, value in rows:
            writer.writerow([f"{timestamp:.9f}", value])


def run_case(name: str, body: Callable[[], None]) -> CaseResult:
    try:
        body()
        return CaseResult(name=name, ok=True)
    except Exception as exc:
        return CaseResult(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}")


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise RuntimeError(detail)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="nucleo_control_timing_") as temp_dir:
        root = Path(temp_dir)

        def clean_capture_passes() -> None:
            path = root / "clean.csv"
            write_capture(path)
            result = analyze_marker(path)
            require(result["pass"], json.dumps(result, indent=2))
            require(result["pulse_count"] == 200, "clean pulse count mismatch")
            require(result["missed_updates"] == 0, "clean capture reported missed ISR")

        def overrun_fails() -> None:
            path = root / "overrun.csv"
            write_capture(path, execution_us=30.0)
            result = analyze_marker(path)
            require(not result["pass"], "execution overrun was accepted")
            require(not result["execution_budget_pass"], "overrun gate did not fail")

        def missed_update_fails() -> None:
            path = root / "missed.csv"
            write_capture(path, skip_index=80)
            result = analyze_marker(path)
            require(not result["pass"], "missing ISR was accepted")
            require(result["missed_updates"] == 1, "missing ISR count mismatch")

        def excessive_jitter_fails() -> None:
            path = root / "jitter.csv"
            write_capture(path, jitter_us=4.0)
            result = analyze_marker(path)
            require(not result["pass"], "excessive jitter was accepted")
            require(not result["period_jitter_pass"], "jitter gate did not fail")

        def coarse_capture_fails() -> None:
            path = root / "coarse.csv"
            write_capture(path)
            result = analyze_marker(
                path,
                selected_sample_rate_hz=1_000_000.0,
                max_sample_period_ns=200.0,
            )
            require(not result["pass"], "coarse Saleae sample rate was accepted")
            require(not result["timing_resolution_pass"], "resolution gate did not fail")

        cases = [
            run_case("clean_capture_passes", clean_capture_passes),
            run_case("overrun_fails", overrun_fails),
            run_case("missed_update_fails", missed_update_fails),
            run_case("excessive_jitter_fails", excessive_jitter_fails),
            run_case("coarse_capture_fails", coarse_capture_fails),
        ]

    failed = [case for case in cases if not case.ok]
    summary = {
        "tool": "nucleo_control_timing_analyze_selftest",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [asdict(case) for case in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
