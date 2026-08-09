#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any


def channel_column(header: list[str], channel: int) -> int:
    target = f"channel{channel}"
    for idx, name in enumerate(header[1:], start=1):
        normalized = "".join(ch.lower() for ch in name if ch.isalnum())
        if target in normalized:
            return idx
    if len(header) > channel + 1:
        return channel + 1
    raise ValueError(f"channel {channel} not found in CSV header")


def load_channel(path: Path, channel: int) -> tuple[list[float], list[int]]:
    with path.open("r", newline="", encoding="utf-8", errors="replace") as stream:
        reader = csv.reader(stream)
        header = next(reader, None)
        if not header:
            raise ValueError("empty CSV")
        column = channel_column(header, channel)
        times: list[float] = []
        values: list[int] = []
        for row in reader:
            if not row or column >= len(row):
                continue
            try:
                timestamp = float(row[0])
            except ValueError:
                continue
            times.append(timestamp)
            values.append(1 if row[column].strip() == "1" else 0)
    if len(times) < 2:
        raise ValueError("CSV must contain at least two data rows")
    if any(times[idx] <= times[idx - 1] for idx in range(1, len(times))):
        raise ValueError("CSV timestamps must be strictly increasing")
    return times, values


def percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[rank]


def active_pulses(times: list[float], values: list[int], active_level: int) -> list[tuple[float, float]]:
    pulses: list[tuple[float, float]] = []
    active_start: float | None = times[0] if values[0] == active_level else None
    for idx in range(1, len(times)):
        if values[idx] == values[idx - 1]:
            continue
        if values[idx] == active_level:
            active_start = times[idx]
        elif active_start is not None:
            pulses.append((active_start, times[idx]))
            active_start = None
    # Incomplete pulses at capture boundaries cannot prove execution time.
    return [pulse for pulse in pulses if pulse[1] > pulse[0]]


def analyze_marker(
    csv_path: Path,
    *,
    channel: int = 7,
    active_level: int = 0,
    expected_hz: float = 20_000.0,
    budget_us: float = 25.0,
    max_period_error_us: float = 2.0,
    min_pulses: int = 100,
    selected_sample_rate_hz: float = 0.0,
    max_sample_period_ns: float = 0.0,
) -> dict[str, Any]:
    if active_level not in (0, 1):
        raise ValueError("active_level must be 0 or 1")
    if expected_hz <= 0.0 or budget_us <= 0.0 or max_period_error_us < 0.0:
        raise ValueError("expected_hz and budget_us must be positive")
    if min_pulses < 2:
        raise ValueError("min_pulses must be at least 2")

    times, values = load_channel(csv_path, channel)
    pulses = active_pulses(times, values, active_level)
    starts = [start for start, _ in pulses]
    durations_us = [(end - start) * 1_000_000.0 for start, end in pulses]
    periods_us = [(starts[idx] - starts[idx - 1]) * 1_000_000.0 for idx in range(1, len(starts))]
    expected_period_us = 1_000_000.0 / expected_hz

    missed_updates = 0
    period_errors_us: list[float] = []
    for period in periods_us:
        period_multiple = max(1, int(round(period / expected_period_us)))
        missed_updates += max(0, period_multiple - 1)
        period_errors_us.append(abs(period - period_multiple * expected_period_us))

    selected_rate = max(0.0, float(selected_sample_rate_hz))
    selected_period_ns = 1_000_000_000.0 / selected_rate if selected_rate > 0.0 else None
    timing_resolution_pass = True
    if max_sample_period_ns > 0.0:
        timing_resolution_pass = bool(
            selected_period_ns is not None and selected_period_ns <= max_sample_period_ns
        )

    pulse_count_pass = len(pulses) >= min_pulses
    execution_budget_pass = bool(durations_us and max(durations_us) <= budget_us)
    no_missed_updates_pass = bool(periods_us and missed_updates == 0)
    period_jitter_pass = bool(
        period_errors_us and max(period_errors_us) <= max_period_error_us
    )
    overall_pass = bool(
        pulse_count_pass
        and execution_budget_pass
        and no_missed_updates_pass
        and period_jitter_pass
        and timing_resolution_pass
    )

    return {
        "tool": "nucleo_control_timing_analyze",
        "csv": str(csv_path),
        "channel": channel,
        "active_level": active_level,
        "capture_duration_s": times[-1] - times[0],
        "expected_hz": expected_hz,
        "expected_period_us": expected_period_us,
        "budget_us": budget_us,
        "max_period_error_us": max_period_error_us,
        "min_pulses": min_pulses,
        "pulse_count": len(pulses),
        "period_count": len(periods_us),
        "missed_updates": missed_updates,
        "execution_us": {
            "min": min(durations_us) if durations_us else None,
            "median": median(durations_us) if durations_us else None,
            "mean": mean(durations_us) if durations_us else None,
            "p99": percentile(durations_us, 0.99),
            "max": max(durations_us) if durations_us else None,
            "max_budget_utilization": (
                max(durations_us) / budget_us if durations_us else None
            ),
        },
        "period_us": {
            "min": min(periods_us) if periods_us else None,
            "median": median(periods_us) if periods_us else None,
            "mean": mean(periods_us) if periods_us else None,
            "max": max(periods_us) if periods_us else None,
        },
        "period_error_us": {
            "p99": percentile(period_errors_us, 0.99),
            "max": max(period_errors_us) if period_errors_us else None,
        },
        "selected_sample_rate_hz": selected_rate,
        "selected_sample_period_ns": selected_period_ns,
        "max_sample_period_ns": max_sample_period_ns,
        "pulse_count_pass": pulse_count_pass,
        "execution_budget_pass": execution_budget_pass,
        "no_missed_updates_pass": no_missed_updates_pass,
        "period_jitter_pass": period_jitter_pass,
        "timing_resolution_pass": timing_resolution_pass,
        "pass": overall_pass,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze the active-low Nucleo control-ISR marker exported by Saleae."
    )
    parser.add_argument("csv", type=Path)
    parser.add_argument("--channel", type=int, default=7)
    parser.add_argument("--active-level", type=int, choices=(0, 1), default=0)
    parser.add_argument("--expected-hz", type=float, default=20_000.0)
    parser.add_argument("--budget-us", type=float, default=25.0)
    parser.add_argument("--max-period-error-us", type=float, default=2.0)
    parser.add_argument("--min-pulses", type=int, default=100)
    parser.add_argument("--selected-sample-rate-hz", type=float, default=0.0)
    parser.add_argument("--max-sample-period-ns", type=float, default=0.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = analyze_marker(
        args.csv,
        channel=args.channel,
        active_level=args.active_level,
        expected_hz=args.expected_hz,
        budget_us=args.budget_us,
        max_period_error_us=args.max_period_error_us,
        min_pulses=args.min_pulses,
        selected_sample_rate_hz=args.selected_sample_rate_hz,
        max_sample_period_ns=args.max_sample_period_ns,
    )
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    print(encoded)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded + "\n", encoding="utf-8")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
