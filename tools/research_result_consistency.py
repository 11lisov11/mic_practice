#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


SCHEMA_VERSION = "mic_ai.research_result_consistency.v1"
DEFAULT_PERCENT_TOLERANCE = 0.001
DEFAULT_RATIO_TOLERANCE = 1.0e-6


@dataclass(frozen=True)
class SourceSpec:
    path: str
    format: str
    parser: str
    dataset: str = ""
    required: bool = True


@dataclass(frozen=True)
class Claim:
    metric_id: str
    dataset: str
    scope: str
    value: float
    unit: str
    canonical_unit: str
    canonical_value: float
    tolerance: float
    source: str
    location: str
    raw: str


DEFAULT_SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        path="research/mic_ai_theory/legacy_mic/three_motor_release/"
        "motor_tuning_acceptance_summary.json",
        format="json",
        parser="legacy_acceptance_json",
        dataset="legacy_mic_three_motor_release",
    ),
    SourceSpec(
        path="research/MIC_AI_RESEARCH_AUDIT_RU.md",
        format="markdown",
        parser="research_audit_markdown",
        dataset="legacy_mic_three_motor_release",
    ),
    SourceSpec(
        path="research/mic_ai_theory/legacy_mic/air56_deployment_reference/README.md",
        format="markdown",
        parser="air56_release_markdown",
        dataset="legacy_mic_three_motor_release",
    ),
    SourceSpec(
        path="research/mic_ai_theory/articles/ieee_manuscript.md",
        format="markdown",
        parser="ieee_markdown",
        dataset="legacy_mic_step28_frozen",
    ),
    SourceSpec(
        path="research/mic_ai_theory/articles/pgups_article_ru.md",
        format="markdown",
        parser="pgups_markdown",
        dataset="pgups_2026_validation",
    ),
)


NUMBER = r"[+\-\N{MINUS SIGN}]?\d+(?:[.,]\d+)?"
UNIT_ALIASES: dict[str, tuple[str, float]] = {
    "%": ("percent", 1.0),
    "pct": ("percent", 1.0),
    "percent": ("percent", 1.0),
    "percentage_point": ("percent", 1.0),
    "percentage_points": ("percent", 1.0),
    "pp": ("percent", 1.0),
    "basis_point": ("percent", 0.01),
    "basis_points": ("percent", 0.01),
    "bp": ("percent", 0.01),
    "count": ("count", 1.0),
    "ratio": ("ratio", 1.0),
    "dimensionless": ("ratio", 1.0),
}


def _parse_number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean is not a numeric result")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        cleaned = value.strip().replace("\N{MINUS SIGN}", "-").replace(",", ".")
        result = float(cleaned)
    else:
        raise ValueError(f"unsupported numeric value {value!r}")
    if not math.isfinite(result):
        raise ValueError(f"non-finite numeric value {value!r}")
    return result


def _normalise_unit(value: float, unit: str) -> tuple[str, float]:
    key = unit.strip().lower().replace(" ", "_")
    if key not in UNIT_ALIASES:
        raise ValueError(f"unsupported unit {unit!r}")
    canonical_unit, scale = UNIT_ALIASES[key]
    return canonical_unit, value * scale


def _default_tolerance(canonical_unit: str) -> float:
    if canonical_unit == "percent":
        return DEFAULT_PERCENT_TOLERANCE
    if canonical_unit == "count":
        return 0.0
    return DEFAULT_RATIO_TOLERANCE


def _make_claim(
    *,
    metric_id: str,
    dataset: str,
    scope: str,
    value: Any,
    unit: str,
    source: str,
    location: str,
    raw: str,
    tolerance: Any | None = None,
) -> Claim:
    metric_id = metric_id.strip()
    dataset = dataset.strip()
    scope = scope.strip()
    if not metric_id or not dataset or not scope:
        raise ValueError("metric_id, dataset and scope must be non-empty")
    parsed_value = _parse_number(value)
    canonical_unit, canonical_value = _normalise_unit(parsed_value, unit)
    if tolerance is None:
        canonical_tolerance = _default_tolerance(canonical_unit)
    else:
        parsed_tolerance = _parse_number(tolerance)
        if parsed_tolerance < 0.0:
            raise ValueError("tolerance must be non-negative")
        _, canonical_tolerance = _normalise_unit(parsed_tolerance, unit)
    return Claim(
        metric_id=metric_id,
        dataset=dataset,
        scope=scope,
        value=parsed_value,
        unit=unit,
        canonical_unit=canonical_unit,
        canonical_value=canonical_value,
        tolerance=canonical_tolerance,
        source=source,
        location=location,
        raw=raw.strip(),
    )


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _claims_from_matches(
    text: str,
    pattern: str,
    *,
    metric_id: str,
    dataset: str,
    scope: str,
    source: str,
    unit: str = "percent",
    group: str = "value",
    tolerance: float | None = None,
    flags: int = re.IGNORECASE,
) -> list[Claim]:
    claims: list[Claim] = []
    for match in re.finditer(pattern, text, flags):
        claims.append(
            _make_claim(
                metric_id=metric_id,
                dataset=dataset,
                scope=scope,
                value=match.group(group),
                unit=unit,
                source=source,
                location=f"line:{_line_number(text, match.start())}",
                raw=match.group(0),
                tolerance=tolerance,
            )
        )
    return claims


def _claim_from_mapping(
    item: dict[str, Any],
    *,
    source: str,
    location: str,
    dataset_fallback: str,
    raw: str,
) -> Claim:
    return _make_claim(
        metric_id=str(item.get("metric_id", "")),
        dataset=str(item.get("dataset", dataset_fallback)),
        scope=str(item.get("scope", "")),
        value=item.get("value"),
        unit=str(item.get("unit", "")),
        tolerance=item.get("tolerance"),
        source=source,
        location=location,
        raw=raw,
    )


def _parse_claims_json(path: Path, spec: SourceSpec) -> list[Claim]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        items = payload.get("research_result_claims")
    else:
        items = payload
    if not isinstance(items, list):
        raise ValueError("JSON must contain a research_result_claims array")
    claims: list[Claim] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"claim at index {index} is not an object")
        claims.append(
            _claim_from_mapping(
                item,
                source=spec.path,
                location=f"research_result_claims[{index}]",
                dataset_fallback=spec.dataset,
                raw=json.dumps(item, ensure_ascii=False, sort_keys=True),
            )
        )
    return claims


def _parse_claims_markdown(path: Path, spec: SourceSpec) -> list[Claim]:
    text = path.read_text(encoding="utf-8-sig")
    pattern = re.compile(
        r"<!--\s*research-result\s*:\s*(?P<payload>\{.*?\})\s*-->",
        re.IGNORECASE,
    )
    claims: list[Claim] = []
    for match in pattern.finditer(text):
        item = json.loads(match.group("payload"))
        if not isinstance(item, dict):
            raise ValueError("research-result annotation must contain a JSON object")
        claims.append(
            _claim_from_mapping(
                item,
                source=spec.path,
                location=f"line:{_line_number(text, match.start())}",
                dataset_fallback=spec.dataset,
                raw=match.group(0),
            )
        )
    return claims


def _parse_legacy_acceptance_json(path: Path, spec: SourceSpec) -> list[Claim]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("expected a non-empty rows array")

    definitions = (
        ("mic.mean_input_power_saving", "avg_power_saving_pct_mean"),
        ("mic.minimum_input_power_saving", "avg_power_saving_pct_min"),
        ("mic.mean_eta_gain", "avg_eta_gain_pct_mean"),
        ("mic.minimum_eta_gain", "avg_eta_gain_pct_min"),
        ("mic.mean_start_stop_power_saving", "start_stop_power_saving_pct_mean"),
    )
    claims: list[Claim] = []
    numeric_rows: list[dict[str, float]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not str(row.get("motor", "")).strip():
            raise ValueError(f"invalid motor row at index {index}")
        motor = str(row["motor"]).strip().lower()
        numeric: dict[str, float] = {}
        for metric_id, field in definitions:
            if field not in row:
                raise ValueError(f"row {index} is missing {field}")
            numeric[field] = _parse_number(row[field])
            claims.append(
                _make_claim(
                    metric_id=metric_id,
                    dataset=spec.dataset,
                    scope=f"motor={motor};aggregation=mean_over_scenarios_and_seeds",
                    value=numeric[field],
                    unit="percent",
                    source=spec.path,
                    location=f"rows[{index}].{field}",
                    raw=f"{field}={row[field]!r}",
                )
            )
        numeric_rows.append(numeric)

    aggregate_scope = "motors=air56,al31,ao2;aggregation=unweighted_motor_mean"
    for metric_id, field in (
        ("mic.mean_input_power_saving", "avg_power_saving_pct_mean"),
        ("mic.mean_eta_gain", "avg_eta_gain_pct_mean"),
        ("mic.mean_start_stop_power_saving", "start_stop_power_saving_pct_mean"),
    ):
        value = statistics.fmean(row[field] for row in numeric_rows)
        claims.append(
            _make_claim(
                metric_id=metric_id,
                dataset=spec.dataset,
                scope=aggregate_scope,
                value=value,
                unit="percent",
                source=spec.path,
                location=f"derived:mean(rows.*.{field})",
                raw=f"unweighted mean of {field}",
            )
        )

    minimum = min(row["avg_power_saving_pct_min"] for row in numeric_rows)
    claims.append(
        _make_claim(
            metric_id="mic.minimum_input_power_saving",
            dataset=spec.dataset,
            scope="motors=air56,al31,ao2;aggregation=minimum_acceptance_value",
            value=minimum,
            unit="percent",
            source=spec.path,
            location="derived:min(rows.*.avg_power_saving_pct_min)",
            raw="minimum of avg_power_saving_pct_min",
        )
    )
    return claims


def _parse_research_audit_markdown(path: Path, spec: SourceSpec) -> list[Claim]:
    text = path.read_text(encoding="utf-8-sig")
    aggregate_scope = "motors=air56,al31,ao2;aggregation=unweighted_motor_mean"
    minimum_scope = "motors=air56,al31,ao2;aggregation=minimum_acceptance_value"
    claims: list[Claim] = []
    claims += _claims_from_matches(
        text,
        rf"среднюю\s+экономию\s+положительной\s+входной\s+мощности\s+`?(?P<value>{NUMBER})\s*%",
        metric_id="mic.mean_input_power_saving",
        dataset=spec.dataset,
        scope=aggregate_scope,
        source=spec.path,
    )
    claims += _claims_from_matches(
        text,
        rf"Среднее\s+снижение\s+`?Pвх\+`?\s+по\s+тр[её]м\s+двигателям\s+равно\s+`?(?P<value>{NUMBER})\s*%",
        metric_id="mic.mean_input_power_saving",
        dataset=spec.dataset,
        scope=aggregate_scope,
        source=spec.path,
    )
    claims += _claims_from_matches(
        text,
        rf"минимальное\s+среднее.*?составило\s+`?(?P<value>{NUMBER})\s*%",
        metric_id="mic.minimum_input_power_saving",
        dataset=spec.dataset,
        scope=minimum_scope,
        source=spec.path,
        flags=re.IGNORECASE | re.DOTALL,
    )
    claims += _claims_from_matches(
        text,
        rf"Минимум\s+показателя.*?равен\s+`?(?P<value>{NUMBER})\s*%",
        metric_id="mic.minimum_input_power_saving",
        dataset=spec.dataset,
        scope=minimum_scope,
        source=spec.path,
        flags=re.IGNORECASE | re.DOTALL,
    )
    claims += _claims_from_matches(
        text,
        rf"Среднее\s+изменение\s+интегрального\s+КПД\s+равно\s+`?(?P<value>{NUMBER})\s*%",
        metric_id="mic.mean_eta_gain",
        dataset=spec.dataset,
        scope=aggregate_scope,
        source=spec.path,
    )
    return claims


def _parse_air56_release_markdown(path: Path, spec: SourceSpec) -> list[Claim]:
    text = path.read_text(encoding="utf-8-sig")
    scope = "motor=air56;aggregation=mean_over_scenarios_and_seeds"
    fields = (
        ("mic.mean_input_power_saving", "avg_power_saving_pct_mean"),
        ("mic.minimum_input_power_saving", "avg_power_saving_pct_min"),
        ("mic.mean_eta_gain", "avg_eta_gain_pct_mean"),
        ("mic.minimum_eta_gain", "avg_eta_gain_pct_min"),
        ("mic.mean_start_stop_power_saving", "start_stop_power_saving_pct_mean"),
    )
    claims: list[Claim] = []
    for metric_id, field in fields:
        claims += _claims_from_matches(
            text,
            rf"`?{re.escape(field)}`?\s*=\s*(?P<value>{NUMBER})\s*%",
            metric_id=metric_id,
            dataset=spec.dataset,
            scope=scope,
            source=spec.path,
        )
    return claims


def _parse_ieee_markdown(path: Path, spec: SourceSpec) -> list[Claim]:
    text = path.read_text(encoding="utf-8-sig")
    aggregate_scope = (
        "motors=air56,al31,ao2;scenarios=speed_step,ramp,load_step,start_stop;"
        "seeds=101,202,303,404,505;aggregation=unweighted_motor_mean"
    )
    claims: list[Claim] = []
    for metric_id, pattern in (
        (
            "mic.mean_input_power_saving",
            rf"MIC\s+mean\s+power\s+saving:\s*`?(?P<value>{NUMBER})\s*%",
        ),
        (
            "mic.mean_eta_gain",
            rf"MIC\s+mean\s+eta\s+gain:\s*`?(?P<value>{NUMBER})\s*%",
        ),
        (
            "mic.mean_start_stop_power_saving",
            rf"Mean\s+`?start_stop`?\s+saving:\s*`?(?P<value>{NUMBER})\s*%",
        ),
    ):
        claims += _claims_from_matches(
            text,
            pattern,
            metric_id=metric_id,
            dataset=spec.dataset,
            scope=aggregate_scope,
            source=spec.path,
        )
    return claims


def _parse_pgups_markdown(path: Path, spec: SourceSpec) -> list[Claim]:
    text = path.read_text(encoding="utf-8-sig")
    full_scope = (
        "motors=air56,al31,ao2;scenarios=5;interval=full;"
        "aggregation=unweighted_motor_mean"
    )
    steady_scope = (
        "motors=air56,al31,ao2;scenarios=5;interval=steady_window;"
        "aggregation=unweighted_motor_mean"
    )
    claims: list[Claim] = []
    russian_pattern = (
        rf"(?:средняя\s+экономия(?:\s+Pвх\+)?|"
        rf"(?:в\s+среднем\s+по\s+тр[её]м\s+двигателям\s+)?экономия\s+Pвх\+)"
        rf"\s+составила\s+(?P<full>{NUMBER})\s*%\s+на\s+полном\s+интервале\s+и\s+"
        rf"(?P<steady>{NUMBER})\s*%\s+в\s+установившемся\s+окне"
    )
    english_pattern = (
        rf"mean\s+input-power\s+saving\s+is\s+(?P<full>{NUMBER})\s*%\s+over\s+the\s+"
        rf"full\s+interval\s+and\s+(?P<steady>{NUMBER})\s*%\s+in\s+the\s+steady\s+window"
    )
    for pattern in (russian_pattern, english_pattern):
        for match in re.finditer(pattern, text, re.IGNORECASE):
            line = f"line:{_line_number(text, match.start())}"
            for group, scope in (("full", full_scope), ("steady", steady_scope)):
                claims.append(
                    _make_claim(
                        metric_id="mic.mean_input_power_saving",
                        dataset=spec.dataset,
                        scope=scope,
                        value=match.group(group),
                        unit="percent",
                        source=spec.path,
                        location=line,
                        raw=match.group(0),
                    )
                )
    return claims


PARSERS: dict[str, Callable[[Path, SourceSpec], list[Claim]]] = {
    "claims_json": _parse_claims_json,
    "claims_markdown": _parse_claims_markdown,
    "legacy_acceptance_json": _parse_legacy_acceptance_json,
    "research_audit_markdown": _parse_research_audit_markdown,
    "air56_release_markdown": _parse_air56_release_markdown,
    "ieee_markdown": _parse_ieee_markdown,
    "pgups_markdown": _parse_pgups_markdown,
}


def _source_issue(spec: SourceSpec, message: str) -> dict[str, Any]:
    return {"source": spec.path, "message": message, "required": spec.required}


def _group_claims(claims: Iterable[Claim]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Claim]] = {}
    for claim in claims:
        key = (claim.metric_id, claim.dataset, claim.scope)
        grouped.setdefault(key, []).append(claim)

    groups: list[dict[str, Any]] = []
    for key in sorted(grouped):
        members = sorted(
            grouped[key],
            key=lambda item: (item.source, item.location, item.canonical_value),
        )
        units = sorted({item.canonical_unit for item in members})
        values = [item.canonical_value for item in members]
        tolerance = min(item.tolerance for item in members)
        conflict_type = ""
        if len(units) != 1:
            status = "conflict"
            conflict_type = "incompatible_units"
            minimum: float | None = None
            maximum: float | None = None
            spread: float | None = None
        else:
            minimum = min(values)
            maximum = max(values)
            spread = max(values) - min(values)
            if spread > tolerance:
                status = "conflict"
                conflict_type = "value_mismatch"
            elif len(members) == 1:
                status = "single_claim"
            else:
                status = "consistent"
        groups.append(
            {
                "metric_id": key[0],
                "dataset": key[1],
                "scope": key[2],
                "comparison_key": {
                    "metric_id": key[0],
                    "dataset": key[1],
                    "scope": key[2],
                },
                "status": status,
                "conflict_type": conflict_type or None,
                "claim_count": len(members),
                "canonical_units": units,
                "minimum": minimum,
                "maximum": maximum,
                "spread": spread,
                "tolerance": tolerance,
                "claims": [asdict(item) for item in members],
            }
        )
    return groups


def analyse(
    root: Path,
    *,
    source_specs: Sequence[SourceSpec] = DEFAULT_SOURCE_SPECS,
    strict: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    claims: list[Claim] = []
    source_reports: list[dict[str, Any]] = []
    source_issues: list[dict[str, Any]] = []

    for spec in source_specs:
        path = root / Path(spec.path)
        source_report: dict[str, Any] = {
            "path": spec.path,
            "format": spec.format,
            "parser": spec.parser,
            "dataset": spec.dataset,
            "required": spec.required,
            "exists": path.is_file(),
            "claim_count": 0,
            "status": "pending",
        }
        if not path.is_file():
            source_report["status"] = "missing"
            source_issues.append(_source_issue(spec, "source file is missing"))
            source_reports.append(source_report)
            continue
        if path.suffix.lower() not in {".json", ".md", ".markdown"}:
            source_report["status"] = "invalid"
            source_issues.append(_source_issue(spec, "source is not JSON or Markdown"))
            source_reports.append(source_report)
            continue
        expected_format = "json" if path.suffix.lower() == ".json" else "markdown"
        if spec.format != expected_format:
            source_report["status"] = "invalid"
            source_issues.append(
                _source_issue(
                    spec,
                    f"declared format {spec.format!r} does not match {expected_format!r}",
                )
            )
            source_reports.append(source_report)
            continue
        parser = PARSERS.get(spec.parser)
        if parser is None:
            source_report["status"] = "invalid"
            source_issues.append(_source_issue(spec, f"unknown parser {spec.parser!r}"))
            source_reports.append(source_report)
            continue
        try:
            extracted = parser(path, spec)
            if not extracted:
                raise ValueError("no declared MIC result claims were extracted")
            claims.extend(extracted)
            source_report["claim_count"] = len(extracted)
            source_report["status"] = "parsed"
        except Exception as exc:
            source_report["status"] = "invalid"
            source_report["error"] = f"{type(exc).__name__}: {exc}"
            source_issues.append(_source_issue(spec, source_report["error"]))
        source_reports.append(source_report)

    groups = _group_claims(claims)
    conflicts = [group for group in groups if group["status"] == "conflict"]
    strict_issues = [issue for issue in source_issues if issue["required"]]
    failed = bool(conflicts) or bool(strict and strict_issues)
    if failed:
        status = "FAIL"
    elif source_issues:
        status = "WARN"
    else:
        status = "PASS"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "strict": bool(strict),
        "status": status,
        "ok": not failed,
        "policy": {
            "comparison_identity": ["metric_id", "dataset", "scope"],
            "conflicts_always_fail": True,
            "strict_required_source_errors_fail": True,
            "incompatible_units_fail": True,
            "default_percent_tolerance": DEFAULT_PERCENT_TOLERANCE,
            "default_ratio_tolerance": DEFAULT_RATIO_TOLERANCE,
        },
        "summary": {
            "source_count": len(source_specs),
            "parsed_source_count": sum(item["status"] == "parsed" for item in source_reports),
            "claim_count": len(claims),
            "comparison_group_count": len(groups),
            "conflict_count": len(conflicts),
            "source_issue_count": len(source_issues),
        },
        "sources": source_reports,
        "source_issues": source_issues,
        "claims": [
            asdict(item)
            for item in sorted(
                claims,
                key=lambda claim: (
                    claim.metric_id,
                    claim.dataset,
                    claim.scope,
                    claim.source,
                    claim.location,
                ),
            )
        ],
        "groups": groups,
        "conflicts": conflicts,
    }


def _write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(
    argv: Sequence[str] | None = None,
    *,
    source_specs: Sequence[SourceSpec] = DEFAULT_SOURCE_SPECS,
) -> int:
    parser = argparse.ArgumentParser(
        description="Check declared MIC research results for contradictory final numbers."
    )
    parser.add_argument("--root", default=".", help="Repository root containing declared sources.")
    parser.add_argument("--json-out", help="Write the machine-readable report to this path.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when a required source is missing, invalid, or yields no claims.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    report = analyse(root, source_specs=source_specs, strict=args.strict)
    if args.json_out:
        output = Path(args.json_out)
        if not output.is_absolute():
            output = root / output
        _write_json(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
