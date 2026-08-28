#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

import research_result_consistency as consistency


FIXTURE_SOURCES = (
    consistency.SourceSpec(
        path="results/final.json",
        format="json",
        parser="claims_json",
        dataset="fixture_set",
    ),
    consistency.SourceSpec(
        path="paper/final.md",
        format="markdown",
        parser="claims_markdown",
        dataset="fixture_set",
    ),
)


def _write_fixture(root: Path, *, markdown_full_value_percent: float) -> None:
    json_path = root / "results" / "final.json"
    markdown_path = root / "paper" / "final.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    json_payload = {
        "research_result_claims": [
            {
                "metric_id": "mic.mean_input_power_saving",
                "dataset": "fixture_set",
                "scope": "interval=full;aggregation=mean",
                "value": 1.8,
                "unit": "percent",
                "tolerance": 0.001,
            },
            {
                "metric_id": "mic.mean_input_power_saving",
                "dataset": "fixture_set",
                "scope": "interval=steady;aggregation=mean",
                "value": 1.31,
                "unit": "percent",
                "tolerance": 0.001,
            },
        ]
    }
    json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    markdown_path.write_text(
        "# Fixture\n\n"
        "<!-- research-result: "
        + json.dumps(
            {
                "metric_id": "mic.mean_input_power_saving",
                "dataset": "fixture_set",
                "scope": "interval=full;aggregation=mean",
                "value": markdown_full_value_percent * 100.0,
                "unit": "basis_points",
                "tolerance": 0.1,
            }
        )
        + " -->\n\n"
        "<!-- research-result: "
        + json.dumps(
            {
                "metric_id": "mic.mean_input_power_saving",
                "dataset": "fixture_set",
                "scope": "interval=diagnostic_only;aggregation=mean",
                "value": 99.0,
                "unit": "percent",
                "tolerance": 0.001,
            }
        )
        + " -->\n",
        encoding="utf-8",
    )


def _run_cli(root: Path) -> tuple[int, dict]:
    report_path = root / "report.json"
    with contextlib.redirect_stdout(io.StringIO()):
        exit_code = consistency.main(
            ["--root", str(root), "--json-out", str(report_path), "--strict"],
            source_specs=FIXTURE_SOURCES,
        )
    return exit_code, json.loads(report_path.read_text(encoding="utf-8"))


def _assert_pass_case() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_fixture(root, markdown_full_value_percent=1.8004)
        exit_code, report = _run_cli(root)
        assert exit_code == 0, report
        assert report["status"] == "PASS", report
        assert report["ok"] is True, report
        assert report["summary"]["conflict_count"] == 0, report
        groups = {
            (group["metric_id"], group["dataset"], group["scope"]): group
            for group in report["groups"]
        }
        full_key = (
            "mic.mean_input_power_saving",
            "fixture_set",
            "interval=full;aggregation=mean",
        )
        diagnostic_key = (
            "mic.mean_input_power_saving",
            "fixture_set",
            "interval=diagnostic_only;aggregation=mean",
        )
        assert groups[full_key]["status"] == "consistent", groups[full_key]
        assert groups[diagnostic_key]["status"] == "single_claim", groups[diagnostic_key]


def _assert_conflict_case() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _write_fixture(root, markdown_full_value_percent=2.1)
        exit_code, report = _run_cli(root)
        assert exit_code == 1, report
        assert report["status"] == "FAIL", report
        assert report["ok"] is False, report
        assert report["summary"]["conflict_count"] == 1, report
        conflict = report["conflicts"][0]
        assert conflict["metric_id"] == "mic.mean_input_power_saving", conflict
        assert conflict["dataset"] == "fixture_set", conflict
        assert conflict["scope"] == "interval=full;aggregation=mean", conflict
        assert conflict["conflict_type"] == "value_mismatch", conflict
        assert conflict["spread"] > conflict["tolerance"], conflict


def main() -> int:
    _assert_pass_case()
    _assert_conflict_case()
    print("PASS: research_result_consistency_selftest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
