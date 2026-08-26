from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from control.cyclic_conformal_reachability import binomial_upper_tail


class _UnattainableThresholdError(ValueError):
    pass


def _probability(value: float, name: str, *, allow_zero: bool = False) -> float:
    value = float(value)
    lower_ok = value >= 0.0 if allow_zero else value > 0.0
    if not math.isfinite(value) or not lower_ok or value >= 1.0:
        interval = "[0, 1)" if allow_zero else "(0, 1)"
        raise ValueError(f"{name} must be finite and in {interval}")
    return value


def critical_successes(
    total: int,
    *,
    lower_bound_threshold: float,
    error_probability: float,
) -> int:
    """Minimum successes whose exact one-sided lower bound reaches the threshold."""

    total = int(total)
    if total <= 0:
        raise ValueError("total must be positive")
    threshold = _probability(lower_bound_threshold, "lower_bound_threshold", allow_zero=True)
    error = _probability(error_probability, "error_probability")
    if threshold == 0.0:
        return 0

    low = 1
    high = total + 1
    while low < high:
        successes = (low + high) // 2
        tail_at_threshold = binomial_upper_tail(successes, total, threshold)
        if tail_at_threshold <= error:
            high = successes
        else:
            low = successes + 1
    if low > total:
        raise _UnattainableThresholdError("the requested lower-bound threshold is unattainable")
    return low


def acceptance_power(
    total: int,
    *,
    assumed_true_coverage: float,
    lower_bound_threshold: float,
    error_probability: float,
) -> tuple[int, float]:
    assumed = _probability(assumed_true_coverage, "assumed_true_coverage")
    critical = critical_successes(
        total,
        lower_bound_threshold=lower_bound_threshold,
        error_probability=error_probability,
    )
    return critical, binomial_upper_tail(critical, int(total), assumed)


def minimum_probe_count(
    *,
    assumed_true_coverage: float,
    lower_bound_threshold: float,
    error_probability: float,
    desired_power: float,
    minimum_total: int = 1,
    maximum_total: int = 10000,
) -> tuple[int, int, float]:
    desired = _probability(desired_power, "desired_power")
    minimum_total = max(1, int(minimum_total))
    maximum_total = int(maximum_total)
    if maximum_total < minimum_total:
        raise ValueError("maximum_total must be at least minimum_total")

    for total in range(minimum_total, maximum_total + 1):
        try:
            critical, power = acceptance_power(
                total,
                assumed_true_coverage=assumed_true_coverage,
                lower_bound_threshold=lower_bound_threshold,
                error_probability=error_probability,
            )
        except _UnattainableThresholdError:
            continue
        if power >= desired:
            return total, critical, power
    raise ValueError("desired power was not reached within maximum_total")


def build_report(
    *,
    assumed_true_coverage: float = 0.95,
    lower_bound_threshold: float = 0.92,
    error_probability: float = 0.01,
    fixed_totals: Sequence[int] = (400, 800),
    desired_powers: Sequence[float] = (0.80, 0.90, 0.95),
) -> dict[str, Any]:
    fixed_designs = []
    for total in fixed_totals:
        critical, power = acceptance_power(
            total,
            assumed_true_coverage=assumed_true_coverage,
            lower_bound_threshold=lower_bound_threshold,
            error_probability=error_probability,
        )
        fixed_designs.append(
            {
                "probe_count": int(total),
                "critical_successes": critical,
                "critical_empirical_coverage": critical / int(total),
                "acceptance_power_at_assumed_coverage": power,
            }
        )

    minimum_designs = []
    for desired in desired_powers:
        total, critical, achieved = minimum_probe_count(
            assumed_true_coverage=assumed_true_coverage,
            lower_bound_threshold=lower_bound_threshold,
            error_probability=error_probability,
            desired_power=desired,
        )
        minimum_designs.append(
            {
                "desired_power": float(desired),
                "minimum_probe_count": total,
                "critical_successes": critical,
                "critical_empirical_coverage": critical / total,
                "achieved_power": achieved,
            }
        )

    joint_two_series_power = None
    design_400 = next((row for row in fixed_designs if row["probe_count"] == 400), None)
    if design_400 is not None:
        joint_two_series_power = design_400["acceptance_power_at_assumed_coverage"] ** 2

    return {
        "schema": "c6_binomial_noninferiority_power/v1",
        "assumed_true_coverage": float(assumed_true_coverage),
        "lower_bound_threshold": float(lower_bound_threshold),
        "one_sided_error_probability": float(error_probability),
        "fixed_designs": fixed_designs,
        "minimum_designs": minimum_designs,
        "joint_power_for_two_independent_400_probe_series": joint_two_series_power,
        "interpretation_boundary": (
            "exact binomial design calculation for independent coverage indicators; it does not repair a failed "
            "locked protocol and does not establish model adequacy, recursive coverage, or hardware validity"
        ),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Exact binomial non-inferiority power plan",
        "",
        f"- Assumed true coverage: `{report['assumed_true_coverage']:.6f}`",
        f"- Exact lower-bound threshold: `{report['lower_bound_threshold']:.6f}`",
        f"- One-sided error probability: `{report['one_sided_error_probability']:.6f}`",
        "",
        "## Fixed designs",
        "",
        "| Probes | Critical successes | Critical empirical coverage | Acceptance power |",
        "|---:|---:|---:|---:|",
    ]
    for row in report["fixed_designs"]:
        lines.append(
            f"| {row['probe_count']} | {row['critical_successes']} | "
            f"{row['critical_empirical_coverage']:.6f} | "
            f"{row['acceptance_power_at_assumed_coverage']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Minimum designs",
            "",
            "| Desired power | Minimum probes | Critical successes | Achieved power |",
            "|---:|---:|---:|---:|",
        ]
    )
    for row in report["minimum_designs"]:
        lines.append(
            f"| {row['desired_power']:.2f} | {row['minimum_probe_count']} | "
            f"{row['critical_successes']} | {row['achieved_power']:.6f} |"
        )
    lines.extend(
        [
            "",
            f"Joint power for two independent 400-probe series: "
            f"`{report['joint_power_for_two_independent_400_probe_series']:.6f}`.",
            "",
            f"Boundary: {report['interpretation_boundary']}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan exact binomial coverage non-inferiority power.")
    parser.add_argument("--assumed-coverage", type=float, default=0.95)
    parser.add_argument("--threshold", type=float, default=0.92)
    parser.add_argument("--error-probability", type=float, default=0.01)
    parser.add_argument("--out-json", type=Path)
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args()

    report = build_report(
        assumed_true_coverage=args.assumed_coverage,
        lower_bound_threshold=args.threshold,
        error_probability=args.error_probability,
    )
    if args.out_json is not None:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
