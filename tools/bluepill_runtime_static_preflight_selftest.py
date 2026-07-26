#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bluepill_runtime_static_preflight as rt


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    detail: str = ""


def probe_with_levels(levels: list[int]) -> dict[str, Any]:
    return {
        "channels": list(range(7)),
        "edges": {str(ch): 0 for ch in range(7)},
        "levels": {str(ch): {"initial": level, "final": level} for ch, level in enumerate(levels)},
    }


def match_subset(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    for key, value in expected.items():
        if actual.get(key) != value:
            return False
    return True


def run_case(name: str, probe: dict[str, Any] | None, analysis: dict[str, Any] | None, expected: dict[str, Any]) -> CaseResult:
    try:
        actual = rt.static_checks(probe, analysis)
        ok = match_subset(actual, expected)
        return CaseResult(
            name=name,
            ok=ok,
            expected=expected,
            actual={key: actual.get(key) for key in expected},
            detail="" if ok else "static check mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name=name,
            ok=False,
            expected=expected,
            actual={},
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_classify_case(name: str, levels: list[int], expected_pattern: str) -> CaseResult:
    expected = {"pattern": expected_pattern}
    try:
        probe = probe_with_levels(levels)
        actual_pattern = rt.classify_static_levels(probe["levels"])
        actual = {"pattern": actual_pattern}
        ok = actual == expected
        return CaseResult(
            name=name,
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "classification mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name=name,
            ok=False,
            expected=expected,
            actual={},
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_analysis_level_fallback_case() -> CaseResult:
    expected = {
        "pass": True,
        "pwm_lines_low": True,
        "em_stop_shutdown_asserted": True,
        "no_overlap_pass": True,
        "pattern": "all_pwm_low_safe",
    }
    try:
        probe = {
            "channels": list(range(7)),
            "edges": {str(ch): 0 for ch in range(7)},
        }
        analysis = {
            "no_overlap_pass": True,
            "channels": {
                str(ch): {"initial": 0, "final": 0}
                for ch in range(7)
            },
        }
        actual = rt.static_checks(probe, analysis)
        ok = match_subset(actual, expected)
        return CaseResult(
            name="analysis_levels_are_used_when_probe_levels_missing",
            ok=ok,
            expected=expected,
            actual={key: actual.get(key) for key in expected},
            detail="" if ok else "fallback level mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="analysis_levels_are_used_when_probe_levels_missing",
            ok=False,
            expected=expected,
            actual={},
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_static_checks_keep_saleae_rate_case() -> CaseResult:
    expected = {
        "pass": True,
        "requested_sample_rate_hz": 24000000,
        "selected_sample_rate_hz": 500000,
        "selected_rate_meets_requested": False,
        "timing_resolution_pass": True,
    }
    try:
        probe = probe_with_levels([0, 0, 0, 0, 0, 0, 0])
        probe["requested_rate"] = 24000000
        probe["selected_rate"] = 500000
        probe["selected_rate_meets_requested"] = False
        analysis = {"no_overlap_pass": True, "timing_resolution_pass": True}
        actual = rt.static_checks(probe, analysis)
        ok = match_subset(actual, expected)
        return CaseResult(
            name="static_checks_keep_saleae_sample_rate_evidence",
            ok=ok,
            expected=expected,
            actual={key: actual.get(key) for key in expected},
            detail="" if ok else "sample-rate evidence mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="static_checks_keep_saleae_sample_rate_evidence",
            ok=False,
            expected=expected,
            actual={},
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_analyze_cmd_includes_selected_rate_case() -> CaseResult:
    expected = {
        "has_selected_rate": True,
        "has_max_period": True,
        "selected_rate": "500000",
        "max_period": "1000.0",
    }
    try:
        cmd = rt.build_analyze_cmd(
            "py",
            rt.Path("C:/repo"),
            rt.Path("C:/repo/tools/run/digital.csv"),
            "0:1,2:3,4:5",
            rt.Path("C:/repo/tools/run/pwm_analysis.json"),
            {"selected_rate": 500000},
            1000.0,
        )
        selected_idx = cmd.index("--selected-sample-rate-hz") if "--selected-sample-rate-hz" in cmd else -1
        max_idx = cmd.index("--max-sample-period-ns") if "--max-sample-period-ns" in cmd else -1
        actual = {
            "has_selected_rate": selected_idx >= 0,
            "has_max_period": max_idx >= 0,
            "selected_rate": cmd[selected_idx + 1] if selected_idx >= 0 else "",
            "max_period": cmd[max_idx + 1] if max_idx >= 0 else "",
        }
        ok = actual == expected
        return CaseResult(
            name="analyze_cmd_includes_selected_saleae_rate",
            ok=ok,
            expected=expected,
            actual=actual,
            detail="" if ok else "analyze command mismatch",
        )
    except Exception as exc:
        return CaseResult(
            name="analyze_cmd_includes_selected_saleae_rate",
            ok=False,
            expected=expected,
            actual={},
            detail=f"{type(exc).__name__}: {exc}",
        )


class PatchScope:
    def __init__(self, **patches: Any) -> None:
        self.patches = patches
        self.old: dict[str, Any] = {}

    def __enter__(self) -> None:
        for name, value in self.patches.items():
            self.old[name] = getattr(rt, name)
            setattr(rt, name, value)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        for name, value in self.old.items():
            setattr(rt, name, value)


def latest_summary(out_root: Path) -> dict[str, Any]:
    summaries = sorted(out_root.glob("bluepill_runtime_static_preflight_*/summary.json"), key=lambda p: p.stat().st_mtime)
    if not summaries:
        raise AssertionError(f"no summary.json under {out_root}")
    return json.loads(summaries[-1].read_text(encoding="utf-8"))


def run_main(args: list[str], out_root: Path, run_cmd_override: Any = None) -> tuple[int, dict[str, Any], list[str]]:
    old_argv = sys.argv[:]
    calls: list[str] = []

    def fake_run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
        calls.append(step)
        if run_cmd_override is not None:
            return run_cmd_override(cmd, cwd, timeout_s, step)
        return {
            "step": step,
            "cmd": cmd,
            "returncode": 0,
            "duration_s": 0.0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }

    try:
        sys.argv = [
            "bluepill_runtime_static_preflight.py",
            "--repo",
            str(Path(__file__).resolve().parents[1]),
            "--out-root",
            str(out_root),
            *args,
        ]
        with PatchScope(
            run_cmd=fake_run_cmd,
            collect_run_metadata=lambda repo: {"repo": str(repo)},
            collect_source_fingerprint=lambda repo: {"sha256": "selftest"},
        ):
            try:
                rc = rt.main()
            except SystemExit as exc:
                rc = int(exc.code or 0)
        return rc, latest_summary(out_root), calls
    finally:
        sys.argv = old_argv


def run_dry_run_plans_strict_static_safe_capture_case() -> CaseResult:
    expected = {
        "rc": 0,
        "pass": True,
        "dry_run": True,
        "calls": ["build_runtime"],
        "capture_requires_static_safe": True,
        "upload_uses_python_module_platformio": True,
        "upload_uses_bare_pio": False,
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            rc, summary, calls = run_main(["--dry-run"], Path(tmp))
            planned = summary.get("planned_commands", {}) if isinstance(summary.get("planned_commands"), dict) else {}
            capture_cmd = " ".join(str(x) for x in planned.get("capture_static", []))
            upload_cmd = [str(x) for x in planned.get("upload_runtime", [])]
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "dry_run": summary.get("dry_run"),
                "calls": calls,
                "capture_requires_static_safe": "--require-static-safe" in capture_cmd,
                "upload_uses_python_module_platformio": upload_cmd[:3] == [sys.executable, "-m", "platformio"],
                "upload_uses_bare_pio": bool(upload_cmd and upload_cmd[0] == "pio"),
            }
            ok = actual == expected
            return CaseResult(
                name="dry_run_plans_strict_static_safe_capture",
                ok=ok,
                expected=expected,
                actual=actual,
                detail="" if ok else "dry-run plan mismatch",
            )
    except Exception as exc:
        return CaseResult(
            name="dry_run_plans_strict_static_safe_capture",
            ok=False,
            expected=expected,
            actual={},
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_capture_command_failure_blocks_pass_case() -> CaseResult:
    expected = {
        "rc": 6,
        "pass": False,
        "capture_ok": False,
        "error": "saleae_static_capture command failed",
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)

            def fake_run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
                ok = step != "saleae_static_capture"
                if step == "saleae_static_capture":
                    outdir = Path(cmd[cmd.index("--outdir") + 1])
                    probe_dir = outdir / "saleae_highlevel_probe_fake"
                    probe_dir.mkdir(parents=True, exist_ok=True)
                    (probe_dir / "summary.json").write_text(
                        json.dumps(
                            {
                                "csv": str(probe_dir / "digital.csv"),
                                "channels": list(range(7)),
                                "edges": {str(ch): 0 for ch in range(7)},
                                "levels": {str(ch): {"initial": 0, "final": 0} for ch in range(7)},
                                "pwm_static_checks": {"pwm_static_safe_pass": True},
                            }
                        ),
                        encoding="utf-8",
                    )
                if step == "analyze_static_pwm":
                    out = Path(cmd[cmd.index("--out") + 1])
                    out.write_text(json.dumps({"no_overlap_pass": True}), encoding="utf-8")
                return {
                    "step": step,
                    "cmd": cmd,
                    "returncode": 0 if ok else 5,
                    "duration_s": 0.0,
                    "stdout": "",
                    "stderr": "" if ok else "capture failed",
                    "ok": ok,
                }

            rc, summary, _calls = run_main(["--confirm-hv-off"], out_root, fake_run_cmd)
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "capture_ok": summary.get("saleae_static_capture_ok"),
                "error": summary.get("error"),
            }
            ok = actual == expected
            return CaseResult(
                name="capture_command_failure_blocks_pass_even_with_good_summary",
                ok=ok,
                expected=expected,
                actual=actual,
                detail="" if ok else "capture command failure was not hard-failed",
            )
    except Exception as exc:
        return CaseResult(
            name="capture_command_failure_blocks_pass_even_with_good_summary",
            ok=False,
            expected=expected,
            actual={},
            detail=f"{type(exc).__name__}: {exc}",
        )


def cases() -> list[CaseResult]:
    probe_static_flag_false = probe_with_levels([0, 0, 0, 0, 0, 0, 0])
    probe_static_flag_false["pwm_static_checks"] = {
        "pwm_static_safe_pass": False,
        "pattern": "low_side_static_high",
    }
    return [
        run_classify_case("classify_all_pwm_low_safe", [0, 0, 0, 0, 0, 0, 0], "all_pwm_low_safe"),
        run_classify_case("classify_low_side_static_high", [0, 1, 0, 1, 0, 1, 0], "low_side_static_high"),
        run_classify_case("classify_high_side_static_high", [1, 0, 1, 0, 1, 0, 0], "high_side_static_high"),
        run_case(
            "safe_static_levels_pass",
            probe_with_levels([0, 0, 0, 0, 0, 0, 0]),
            {"no_overlap_pass": True},
            {
                "pass": True,
                "channels_ok": True,
                "no_edges": True,
                "pwm_lines_low": True,
                "em_stop_shutdown_asserted": True,
                "no_overlap_pass": True,
                "pattern": "all_pwm_low_safe",
            },
        ),
        run_case(
            "low_side_static_high_fails",
            probe_with_levels([0, 1, 0, 1, 0, 1, 0]),
            {"no_overlap_pass": True},
            {
                "pass": False,
                "pwm_lines_low": False,
                "em_stop_shutdown_asserted": True,
                "no_overlap_pass": True,
                "pattern": "low_side_static_high",
            },
        ),
        run_case(
            "em_stop_shutdown_pin_high_fails",
            probe_with_levels([0, 0, 0, 0, 0, 0, 1]),
            {"no_overlap_pass": True},
            {
                "pass": False,
                "pwm_lines_low": True,
                "em_stop_shutdown_asserted": False,
                "no_overlap_pass": True,
                "pattern": "all_pwm_low_safe",
            },
        ),
        run_case(
            "missing_overlap_analysis_fails",
            probe_with_levels([0, 0, 0, 0, 0, 0, 0]),
            None,
            {
                "pass": False,
                "pwm_lines_low": True,
                "em_stop_shutdown_asserted": True,
                "no_overlap_pass": False,
                "pattern": "all_pwm_low_safe",
            },
        ),
        run_case(
            "probe_static_flag_false_fails",
            probe_static_flag_false,
            {"no_overlap_pass": True},
            {
                "pass": False,
                "pwm_lines_low": True,
                "probe_pwm_static_safe_pass": False,
                "pattern": "all_pwm_low_safe",
            },
        ),
        run_case(
            "missing_probe_summary_fails",
            None,
            {"no_overlap_pass": True},
            {
                "pass": False,
                "error": "missing Saleae probe summary",
            },
        ),
        run_analysis_level_fallback_case(),
        run_static_checks_keep_saleae_rate_case(),
        run_analyze_cmd_includes_selected_rate_case(),
        run_dry_run_plans_strict_static_safe_capture_case(),
        run_capture_command_failure_blocks_pass_case(),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "bluepill_runtime_static_preflight_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
