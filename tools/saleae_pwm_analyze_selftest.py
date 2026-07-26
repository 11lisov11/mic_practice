#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CHANNELS = [0, 1, 2, 3, 4, 5]
PAIRS = "0:1,2:3,4:5"


@dataclass
class CaseResult:
    name: str
    ok: bool
    detail: str = ""
    analyzer_returncode: int | None = None
    analysis: dict[str, Any] | None = None


def write_csv(path: Path, rows: list[tuple[float, list[int]]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Time [s]", *[f"Channel {ch}" for ch in CHANNELS]])
        for t, vals in rows:
            writer.writerow([f"{t:.7f}", *[str(int(v)) for v in vals]])


def replicate_pair_rows(pair_rows: list[tuple[float, int, int]]) -> list[tuple[float, list[int]]]:
    rows: list[tuple[float, list[int]]] = []
    for t, hi, lo in pair_rows:
        rows.append((t, [hi, lo, hi, lo, hi, lo]))
    return rows


def no_overlap_pwm_rows() -> list[tuple[float, list[int]]]:
    return replicate_pair_rows(
        [
            (0.0000, 0, 0),
            (0.0010, 1, 0),
            (0.0020, 0, 0),
            (0.0022, 0, 1),
            (0.0030, 0, 0),
            (0.0032, 1, 0),
            (0.0040, 0, 0),
            (0.0042, 0, 1),
            (0.0050, 0, 0),
            (0.0052, 1, 0),
            (0.0060, 0, 0),
        ]
    )


def overlap_pwm_rows() -> list[tuple[float, list[int]]]:
    return replicate_pair_rows(
        [
            (0.0000, 0, 0),
            (0.0010, 1, 0),
            (0.0015, 1, 1),
            (0.0020, 0, 1),
            (0.0025, 0, 0),
            (0.0030, 1, 0),
            (0.0035, 1, 1),
            (0.0040, 0, 1),
            (0.0045, 0, 0),
            (0.0050, 1, 0),
            (0.0055, 0, 0),
        ]
    )


def no_pwm_rows() -> list[tuple[float, list[int]]]:
    return [
        (0.0000, [0, 1, 0, 1, 0, 1]),
        (0.0060, [0, 1, 0, 1, 0, 1]),
    ]


def run_analyzer(
    repo: Path,
    csv_path: Path,
    out_path: Path,
    expect_pwm: bool,
    *,
    use_csv_option: bool = False,
    max_sample_period_ns: float = 0.0,
    selected_sample_rate_hz: float = 0.0,
) -> tuple[int, dict[str, Any] | None, str]:
    cmd = [
        sys.executable,
        "-u",
        str(repo / "tools" / "saleae_pwm_analyze.py"),
        "--pairs",
        PAIRS,
        "--out",
        str(out_path),
    ]
    if use_csv_option:
        cmd[3:3] = ["--csv", str(csv_path)]
    else:
        cmd.insert(3, str(csv_path))
    if expect_pwm:
        cmd.append("--expect-pwm")
    if max_sample_period_ns > 0.0:
        cmd += ["--max-sample-period-ns", str(max_sample_period_ns)]
    if selected_sample_rate_hz > 0.0:
        cmd += ["--selected-sample-rate-hz", str(selected_sample_rate_hz)]
    proc = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, timeout=30.0)
    data = None
    if out_path.exists():
        data = json.loads(out_path.read_text(encoding="utf-8"))
    return proc.returncode, data, (proc.stdout or "") + (proc.stderr or "")


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise RuntimeError(msg)


def run_case(
    repo: Path,
    root: Path,
    name: str,
    rows: list[tuple[float, list[int]]],
    expect_pwm: bool,
    expect_rc: int,
    expectations: dict[str, Any],
    *,
    use_csv_option: bool = False,
    max_sample_period_ns: float = 0.0,
    selected_sample_rate_hz: float = 0.0,
) -> CaseResult:
    csv_path = root / f"{name}.csv"
    out_path = root / f"{name}.json"
    write_csv(csv_path, rows)
    rc, data, text = run_analyzer(
        repo,
        csv_path,
        out_path,
        expect_pwm,
        use_csv_option=use_csv_option,
        max_sample_period_ns=max_sample_period_ns,
        selected_sample_rate_hz=selected_sample_rate_hz,
    )
    try:
        assert_true(rc == expect_rc, f"returncode expected {expect_rc}, got {rc}; output={text}")
        assert_true(isinstance(data, dict), "missing analysis json")
        for key, expected in expectations.items():
            actual = data.get(key)
            assert_true(actual == expected, f"{key}: expected {expected!r}, got {actual!r}")
        if name == "overlap_pwm":
            assert_true(any(pair.get("both_high_seen") for pair in data["pairs"].values()), "overlap not detected in any pair")
        if name == "no_overlap_pwm":
            assert_true(all(pair.get("no_overlap") for pair in data["pairs"].values()), "no-overlap case reported overlap")
        return CaseResult(name=name, ok=True, analyzer_returncode=rc, analysis=data)
    except Exception as exc:
        return CaseResult(name=name, ok=False, detail=f"{type(exc).__name__}: {exc}", analyzer_returncode=rc, analysis=data)


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="saleae_pwm_analyze_selftest_") as tmp:
        root = Path(tmp)
        cases = [
            run_case(
                repo,
                root,
                "no_overlap_pwm",
                no_overlap_pwm_rows(),
                True,
                0,
                {
                    "pass": True,
                    "expect_pwm": True,
                    "pass_meaning": "no_overlap_and_pwm_activity",
                    "overlap_analysis_pass": True,
                    "no_overlap_pass": True,
                    "pwm_activity_pass": True,
                },
            ),
            run_case(
                repo,
                root,
                "no_overlap_pwm_csv_option",
                no_overlap_pwm_rows(),
                True,
                0,
                {
                    "pass": True,
                    "expect_pwm": True,
                    "pass_meaning": "no_overlap_and_pwm_activity",
                    "overlap_analysis_pass": True,
                    "no_overlap_pass": True,
                    "pwm_activity_pass": True,
                },
                use_csv_option=True,
            ),
            run_case(
                repo,
                root,
                "overlap_pwm",
                overlap_pwm_rows(),
                True,
                1,
                {"pass": False, "expect_pwm": True, "overlap_analysis_pass": False, "no_overlap_pass": False, "pwm_activity_pass": True},
            ),
            run_case(
                repo,
                root,
                "coarse_timing_fails_when_resolution_required",
                no_overlap_pwm_rows(),
                True,
                1,
                {
                    "pass": False,
                    "expect_pwm": True,
                    "overlap_analysis_pass": True,
                    "no_overlap_pass": True,
                    "pwm_activity_pass": True,
                    "timing_resolution_pass": False,
                },
                max_sample_period_ns=1_000.0,
                selected_sample_rate_hz=500_000.0,
            ),
            run_case(
                repo,
                root,
                "no_pwm",
                no_pwm_rows(),
                True,
                1,
                {"pass": False, "expect_pwm": True, "overlap_analysis_pass": True, "no_overlap_pass": True, "pwm_activity_pass": False},
            ),
            run_case(
                repo,
                root,
                "no_pwm_static_overlap_only",
                no_pwm_rows(),
                False,
                0,
                {
                    "pass": True,
                    "expect_pwm": False,
                    "pass_meaning": "no_overlap_only_pwm_activity_diagnostic",
                    "overlap_analysis_pass": True,
                    "no_overlap_pass": True,
                    "pwm_activity_pass": False,
                },
            ),
        ]

    failed = [c for c in cases if not c.ok]
    summary = {
        "tool": "saleae_pwm_analyze_selftest",
        "pass": not failed,
        "passed": len(cases) - len(failed),
        "failed": len(failed),
        "cases": [c.__dict__ for c in cases],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
