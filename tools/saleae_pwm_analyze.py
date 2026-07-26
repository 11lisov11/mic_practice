#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def channel_column(header: list[str], channel: int) -> int:
    target = f"channel{channel}"
    for idx, name in enumerate(header[1:], start=1):
        norm = "".join(ch.lower() for ch in name if ch.isalnum())
        if target in norm:
            return idx
    if len(header) > channel + 1:
        return channel + 1
    raise ValueError(f"channel {channel} not found in CSV header")


def load_csv(path: Path, channels: list[int]) -> tuple[list[float], dict[int, list[int]]]:
    with path.open("r", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            raise ValueError("empty CSV")
        cols = {ch: channel_column(header, ch) for ch in channels}
        times: list[float] = []
        values = {ch: [] for ch in channels}
        for row in reader:
            if not row:
                continue
            try:
                t = float(row[0])
            except ValueError:
                continue
            times.append(t)
            for ch, col in cols.items():
                values[ch].append(1 if col < len(row) and row[col].strip() == "1" else 0)
    if len(times) < 2:
        raise ValueError("CSV must contain at least two data rows")
    return times, values


def csv_row_timing(times: list[float]) -> dict[str, Any]:
    intervals = [
        times[idx + 1] - times[idx]
        for idx in range(len(times) - 1)
        if times[idx + 1] > times[idx]
    ]
    if not intervals:
        return {
            "samples": len(times),
            "intervals": 0,
            "min_step_s": None,
            "max_step_s": None,
            "mean_step_s": None,
            "inferred_sample_rate_hz": None,
        }
    mean_step = sum(intervals) / len(intervals)
    return {
        "samples": len(times),
        "intervals": len(intervals),
        "min_step_s": min(intervals),
        "max_step_s": max(intervals),
        "mean_step_s": mean_step,
        "inferred_sample_rate_hz": (1.0 / mean_step) if mean_step > 0.0 else None,
    }


def transitions(times: list[float], vals: list[int]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx in range(1, len(times)):
        if vals[idx] != vals[idx - 1]:
            out.append({"time": times[idx], "from": vals[idx - 1], "to": vals[idx]})
    return out


def high_time(times: list[float], vals: list[int]) -> float:
    total = 0.0
    for idx in range(len(times) - 1):
        dt = times[idx + 1] - times[idx]
        if dt > 0.0 and vals[idx] == 1:
            total += dt
    return total


def channel_summary(times: list[float], vals: list[int]) -> dict[str, Any]:
    tr = transitions(times, vals)
    rising = [e["time"] for e in tr if e["from"] == 0 and e["to"] == 1]
    falling = [e["time"] for e in tr if e["from"] == 1 and e["to"] == 0]
    duration = times[-1] - times[0]
    freq = 0.0
    if len(rising) >= 2:
        periods = [rising[i] - rising[i - 1] for i in range(1, len(rising)) if rising[i] > rising[i - 1]]
        if periods:
            freq = 1.0 / (sum(periods) / len(periods))
    return {
        "initial": vals[0],
        "final": vals[-1],
        "edges": len(tr),
        "rising_edges": len(rising),
        "falling_edges": len(falling),
        "high_time_s": high_time(times, vals),
        "duty_ratio": (high_time(times, vals) / duration) if duration > 0.0 else 0.0,
        "freq_hz_from_rising": freq,
    }


def pair_summary(times: list[float], high_vals: list[int], low_vals: list[int]) -> dict[str, Any]:
    duration = times[-1] - times[0]
    overlap = 0.0
    both_low = 0.0
    for idx in range(len(times) - 1):
        dt = times[idx + 1] - times[idx]
        if dt <= 0.0:
            continue
        if high_vals[idx] == 1 and low_vals[idx] == 1:
            overlap += dt
        if high_vals[idx] == 0 and low_vals[idx] == 0:
            both_low += dt

    high_tr = transitions(times, high_vals)
    low_tr = transitions(times, low_vals)
    low_rise = [e["time"] for e in low_tr if e["from"] == 0 and e["to"] == 1]
    high_rise = [e["time"] for e in high_tr if e["from"] == 0 and e["to"] == 1]
    low_fall = [e["time"] for e in low_tr if e["from"] == 1 and e["to"] == 0]
    high_fall = [e["time"] for e in high_tr if e["from"] == 1 and e["to"] == 0]

    gaps: list[float] = []
    for t in high_fall:
        after = [x for x in low_rise if x >= t]
        if after:
            gaps.append(after[0] - t)
    for t in low_fall:
        after = [x for x in high_rise if x >= t]
        if after:
            gaps.append(after[0] - t)

    return {
        "overlap_high_s": overlap,
        "overlap_ratio": (overlap / duration) if duration > 0.0 else 0.0,
        "both_low_s": both_low,
        "both_low_ratio": (both_low / duration) if duration > 0.0 else 0.0,
        "both_high_seen": overlap > 0.0,
        "min_gap_s": min(gaps) if gaps else None,
        "gap_count": len(gaps),
        "no_overlap": overlap == 0.0,
    }


def parse_pairs(raw: str) -> list[tuple[str, int, int]]:
    pairs: list[tuple[str, int, int]] = []
    names = ["U", "V", "W", "X", "Y", "Z"]
    for idx, token in enumerate(x.strip() for x in raw.split(",") if x.strip()):
        if ":" not in token:
            raise ValueError(f"bad pair {token!r}; expected H:L")
        a, b = token.split(":", 1)
        pairs.append((names[idx] if idx < len(names) else f"P{idx}", int(a), int(b)))
    return pairs


def analyze_csv(
    csv_path: Path,
    pairs_raw: str = "0:1,2:3,4:5",
    expect_pwm: bool = False,
    max_sample_period_ns: float = 0.0,
    selected_sample_rate_hz: float = 0.0,
) -> dict[str, Any]:
    pairs = parse_pairs(pairs_raw)
    channels = sorted({ch for _, hi, lo in pairs for ch in (hi, lo)})
    times, values = load_csv(csv_path, channels)
    row_timing = csv_row_timing(times)
    max_sample_period_s = max(0.0, float(max_sample_period_ns)) * 1e-9
    selected_rate = max(0.0, float(selected_sample_rate_hz))
    selected_sample_period_ns = (1_000_000_000.0 / selected_rate) if selected_rate > 0.0 else None
    timing_resolution_pass = True
    if max_sample_period_s > 0.0:
        timing_resolution_pass = bool(selected_rate > 0.0 and (1.0 / selected_rate) <= max_sample_period_s)
    result: dict[str, Any] = {
        "csv": str(csv_path),
        "duration_s": times[-1] - times[0],
        "csv_row_timing": row_timing,
        "csv_row_timing_note": "Saleae CSV rows may be transition-compressed; use selected_sample_rate_hz for timing proof.",
        "selected_sample_rate_hz": selected_rate,
        "selected_sample_period_ns": selected_sample_period_ns,
        "max_sample_period_ns": float(max_sample_period_ns),
        "timing_resolution_pass": timing_resolution_pass,
        "channels": {str(ch): channel_summary(times, values[ch]) for ch in channels},
        "pairs": {},
    }
    for name, hi, lo in pairs:
        result["pairs"][name] = {
            "high_channel": hi,
            "low_channel": lo,
            **pair_summary(times, values[hi], values[lo]),
        }

    no_overlap = all(pair["no_overlap"] for pair in result["pairs"].values())
    has_pwm = any(ch["edges"] >= 4 for ch in result["channels"].values())
    result["pass"] = bool(no_overlap and (has_pwm if expect_pwm else True) and timing_resolution_pass)
    result["expect_pwm"] = bool(expect_pwm)
    result["pass_meaning"] = "no_overlap_and_pwm_activity" if expect_pwm else "no_overlap_only_pwm_activity_diagnostic"
    result["overlap_analysis_pass"] = bool(no_overlap)
    result["no_overlap_pass"] = bool(no_overlap)
    result["pwm_activity_pass"] = bool(has_pwm)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze Saleae digital CSV for PWM pair overlap and coarse timing.")
    ap.add_argument("csv", nargs="?", type=Path, help="Saleae digital CSV path.")
    ap.add_argument("--csv", dest="csv_opt", type=Path, help="Saleae digital CSV path; kept for script/runbook compatibility.")
    ap.add_argument("--pairs", default="0:1,2:3,4:5")
    ap.add_argument("--expect-pwm", action="store_true")
    ap.add_argument(
        "--max-sample-period-ns",
        type=float,
        default=0.0,
        help="Optional hard timing-resolution gate. 0 disables the gate.",
    )
    ap.add_argument(
        "--selected-sample-rate-hz",
        type=float,
        default=0.0,
        help="Effective Saleae sample rate from the capture summary; required when --max-sample-period-ns is used.",
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    csv_path = args.csv_opt or args.csv
    if csv_path is None:
        ap.error("CSV path is required, either as positional argument or --csv PATH")
    if args.csv_opt is not None and args.csv is not None and args.csv_opt != args.csv:
        ap.error("CSV path was provided twice with different values")

    result = analyze_csv(
        csv_path,
        args.pairs,
        args.expect_pwm,
        args.max_sample_period_ns,
        args.selected_sample_rate_hz,
    )

    text = json.dumps(result, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
