#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import bluepill_static_low_preflight as sl


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    detail: str = ""


def latest_summary(out_root: Path) -> dict[str, Any]:
    summaries = sorted(out_root.glob("bluepill_static_low_preflight_*/summary.json"), key=lambda p: p.stat().st_mtime)
    if not summaries:
        raise AssertionError(f"no summary.json under {out_root}")
    return json.loads(summaries[-1].read_text(encoding="utf-8"))


class PatchScope:
    def __init__(self, **patches: Any) -> None:
        self.patches = patches
        self.old: dict[str, Any] = {}

    def __enter__(self) -> None:
        for name, value in self.patches.items():
            self.old[name] = getattr(sl, name)
            setattr(sl, name, value)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        for name, value in self.old.items():
            setattr(sl, name, value)


def run_main(args: list[str], out_root: Path, run_cmd: Callable[..., dict[str, Any]] | None = None) -> tuple[int, dict[str, Any]]:
    old_argv = sys.argv[:]
    calls: list[str] = []

    def default_run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
        return {
            "step": step,
            "cmd": cmd,
            "returncode": 0,
            "duration_s": 0.0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }

    def wrapped_run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
        calls.append(step)
        if run_cmd is not None:
            return run_cmd(cmd, cwd, timeout_s, step)
        return default_run_cmd(cmd, cwd, timeout_s, step)

    try:
        sys.argv = [
            "bluepill_static_low_preflight.py",
            "--repo",
            str(Path(__file__).resolve().parents[1]),
            "--out-root",
            str(out_root),
            *args,
        ]
        with PatchScope(
            run_cmd=wrapped_run_cmd,
            collect_run_metadata=lambda repo: {"repo": str(repo)},
            collect_source_fingerprint=lambda repo: {"sha256": "selftest"},
        ):
            try:
                rc = sl.main()
            except SystemExit as exc:
                rc = int(exc.code or 0)
        summary = latest_summary(out_root)
        summary["_run_cmd_calls"] = calls
        return rc, summary
    finally:
        sys.argv = old_argv


def run_requires_hv_off_case() -> CaseResult:
    expected = {
        "rc": 2,
        "pass": False,
        "confirm_hv_off": False,
        "error": "--confirm-hv-off is required before uploading static-low diagnostic firmware",
        "calls": [],
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            rc, summary = run_main([], out_root)
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "confirm_hv_off": summary.get("confirm_hv_off"),
                "error": summary.get("error"),
                "calls": summary.get("_run_cmd_calls"),
            }
            ok = actual == expected
            return CaseResult("requires_confirm_hv_off_before_upload", ok, expected, actual, "" if ok else "confirm gate mismatch")
    except Exception as exc:
        return CaseResult("requires_confirm_hv_off_before_upload", False, expected, {}, f"{type(exc).__name__}: {exc}")


def run_dry_run_plans_restore_case() -> CaseResult:
    expected = {
        "rc": 0,
        "pass": True,
        "dry_run": True,
        "calls": ["build_static_low", "build_restore_runtime"],
        "test_env": "bluepill_static_low_test",
        "restore_env": "bluepill_uart_pwm",
        "restore_attempted": False,
        "has_upload_static_low": True,
        "has_restore_runtime": True,
        "capture_requires_static_safe": True,
        "upload_static_low_uses_python_module_platformio": True,
        "restore_uses_python_module_platformio": True,
        "upload_static_low_uses_bare_pio": False,
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            rc, summary = run_main(["--dry-run"], out_root)
            planned = summary.get("planned_commands", {}) if isinstance(summary.get("planned_commands"), dict) else {}
            upload_cmd = " ".join(str(x) for x in planned.get("upload_static_low", []))
            restore_cmd = " ".join(str(x) for x in planned.get("restore_runtime", []))
            capture_cmd = " ".join(str(x) for x in planned.get("capture_static_low", []))
            upload_parts = [str(x) for x in planned.get("upload_static_low", [])]
            restore_parts = [str(x) for x in planned.get("restore_runtime", [])]
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "dry_run": summary.get("dry_run"),
                "calls": summary.get("_run_cmd_calls"),
                "test_env": summary.get("test_env"),
                "restore_env": summary.get("restore_env"),
                "restore_attempted": summary.get("restore_attempted"),
                "has_upload_static_low": "-e bluepill_static_low_test -t upload" in upload_cmd,
                "has_restore_runtime": "-e bluepill_uart_pwm -t upload" in restore_cmd,
                "capture_requires_static_safe": "--require-static-safe" in capture_cmd,
                "upload_static_low_uses_python_module_platformio": upload_parts[:3] == [sys.executable, "-m", "platformio"],
                "restore_uses_python_module_platformio": restore_parts[:3] == [sys.executable, "-m", "platformio"],
                "upload_static_low_uses_bare_pio": bool(upload_parts and upload_parts[0] == "pio"),
            }
            ok = actual == expected
            return CaseResult("dry_run_builds_and_plans_runtime_restore", ok, expected, actual, "" if ok else "dry-run plan mismatch")
    except Exception as exc:
        return CaseResult("dry_run_builds_and_plans_runtime_restore", False, expected, {}, f"{type(exc).__name__}: {exc}")


def run_success_restores_runtime_case() -> CaseResult:
    expected = {
        "rc": 0,
        "pass": True,
        "restored": True,
        "restore_attempted": True,
        "pattern": "all_pwm_low_safe",
        "calls": [
            "build_static_low",
            "build_restore_runtime",
            "upload_static_low",
            "saleae_static_low_capture",
            "analyze_static_low",
            "restore_runtime",
        ],
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            fake_probe = out_root / "probe_summary.json"

            def fake_read_json(path: Path | None) -> dict[str, Any] | None:
                if path is None:
                    return None
                if Path(path).name == "pwm_analysis.json":
                    return {"no_overlap_pass": True}
                return {"csv": str(out_root / "digital.csv"), "channels": list(range(7))}

            with PatchScope(
                rt=type(
                    "FakeRuntimeStatic",
                    (),
                    {
                        "latest_probe_summary": staticmethod(lambda run_dir: fake_probe),
                        "read_json": staticmethod(fake_read_json),
                        "build_analyze_cmd": staticmethod(lambda py, repo, csv, pairs, out, probe, max_ns: [py, "-u", "analyze"]),
                        "static_checks": staticmethod(lambda probe, analysis: {"pass": True, "pattern": "all_pwm_low_safe"}),
                    },
                )
            ):
                rc, summary = run_main(["--confirm-hv-off"], out_root)
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "restored": summary.get("restored"),
                "restore_attempted": summary.get("restore_attempted"),
                "pattern": (summary.get("static_checks") or {}).get("pattern"),
                "calls": summary.get("_run_cmd_calls"),
            }
            ok = actual == expected
            return CaseResult("confirmed_run_restores_runtime_after_capture", ok, expected, actual, "" if ok else "restore flow mismatch")
    except Exception as exc:
        return CaseResult("confirmed_run_restores_runtime_after_capture", False, expected, {}, f"{type(exc).__name__}: {exc}")


def run_restore_failure_overrides_success_case() -> CaseResult:
    expected = {
        "rc": 7,
        "pass": False,
        "restored": False,
        "restore_attempted": True,
        "error": "restore_runtime failed",
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            fake_probe = out_root / "probe_summary.json"

            def fake_run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
                ok = step != "restore_runtime"
                return {
                    "step": step,
                    "cmd": cmd,
                    "returncode": 0 if ok else 1,
                    "duration_s": 0.0,
                    "stdout": "",
                    "stderr": "" if ok else "restore failed",
                    "ok": ok,
                }

            def fake_read_json(path: Path | None) -> dict[str, Any] | None:
                if path is None:
                    return None
                if Path(path).name == "pwm_analysis.json":
                    return {"no_overlap_pass": True}
                return {"csv": str(out_root / "digital.csv"), "channels": list(range(7))}

            with PatchScope(
                rt=type(
                    "FakeRuntimeStatic",
                    (),
                    {
                        "latest_probe_summary": staticmethod(lambda run_dir: fake_probe),
                        "read_json": staticmethod(fake_read_json),
                        "build_analyze_cmd": staticmethod(lambda py, repo, csv, pairs, out, probe, max_ns: [py, "-u", "analyze"]),
                        "static_checks": staticmethod(lambda probe, analysis: {"pass": True, "pattern": "all_pwm_low_safe"}),
                    },
                )
            ):
                rc, summary = run_main(["--confirm-hv-off"], out_root, fake_run_cmd)
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "restored": summary.get("restored"),
                "restore_attempted": summary.get("restore_attempted"),
                "error": summary.get("error"),
            }
            ok = actual == expected
            return CaseResult("restore_failure_returns_hard_error", ok, expected, actual, "" if ok else "restore failure mismatch")
    except Exception as exc:
        return CaseResult("restore_failure_returns_hard_error", False, expected, {}, f"{type(exc).__name__}: {exc}")


def run_capture_command_failure_blocks_pass_case() -> CaseResult:
    expected = {
        "rc": 6,
        "pass": False,
        "restored": True,
        "capture_ok": False,
        "error": "saleae_static_low_capture command failed",
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            fake_probe = out_root / "probe_summary.json"

            def fake_run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
                ok = step != "saleae_static_low_capture"
                return {
                    "step": step,
                    "cmd": cmd,
                    "returncode": 0 if ok else 5,
                    "duration_s": 0.0,
                    "stdout": "",
                    "stderr": "" if ok else "capture failed",
                    "ok": ok,
                }

            def fake_read_json(path: Path | None) -> dict[str, Any] | None:
                if path is None:
                    return None
                if Path(path).name == "pwm_analysis.json":
                    return {"no_overlap_pass": True}
                return {"csv": str(out_root / "digital.csv"), "channels": list(range(7))}

            with PatchScope(
                rt=type(
                    "FakeRuntimeStatic",
                    (),
                    {
                        "latest_probe_summary": staticmethod(lambda run_dir: fake_probe),
                        "read_json": staticmethod(fake_read_json),
                        "build_analyze_cmd": staticmethod(lambda py, repo, csv, pairs, out, probe, max_ns: [py, "-u", "analyze"]),
                        "static_checks": staticmethod(lambda probe, analysis: {"pass": True, "pattern": "all_pwm_low_safe"}),
                    },
                )
            ):
                rc, summary = run_main(["--confirm-hv-off"], out_root, fake_run_cmd)
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "restored": summary.get("restored"),
                "capture_ok": summary.get("saleae_static_low_capture_ok"),
                "error": summary.get("error"),
            }
            ok = actual == expected
            return CaseResult(
                "capture_command_failure_blocks_pass_even_with_good_summary",
                ok,
                expected,
                actual,
                "" if ok else "capture command failure was not hard-failed",
            )
    except Exception as exc:
        return CaseResult(
            "capture_command_failure_blocks_pass_even_with_good_summary",
            False,
            expected,
            {},
            f"{type(exc).__name__}: {exc}",
        )


def run_build_failure_does_not_restore_case() -> CaseResult:
    expected = {
        "rc": 3,
        "pass": False,
        "diagnostic_upload_attempted": False,
        "restore_attempted": False,
        "restored": False,
        "error": "build_static_low failed",
        "calls": ["build_static_low"],
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)

            def fake_run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
                ok = step != "build_static_low"
                return {
                    "step": step,
                    "cmd": cmd,
                    "returncode": 0 if ok else 1,
                    "duration_s": 0.0,
                    "stdout": "",
                    "stderr": "" if ok else "build failed",
                    "ok": ok,
                }

            rc, summary = run_main(["--confirm-hv-off"], out_root, fake_run_cmd)
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "diagnostic_upload_attempted": summary.get("diagnostic_upload_attempted"),
                "restore_attempted": summary.get("restore_attempted"),
                "restored": summary.get("restored"),
                "error": summary.get("error"),
                "calls": summary.get("_run_cmd_calls"),
            }
            ok = actual == expected
            return CaseResult("build_failure_does_not_touch_restore_upload", ok, expected, actual, "" if ok else "build failure restore mismatch")
    except Exception as exc:
        return CaseResult("build_failure_does_not_touch_restore_upload", False, expected, {}, f"{type(exc).__name__}: {exc}")


def run_static_low_conclusion_case() -> CaseResult:
    expected = {
        "pass_result": "static_low_pin_drive_path_ok",
        "pass_next": ["run_runtime_static_preflight"],
        "fail_result": "static_low_pin_drive_path_failed",
        "fail_next": ["inspect_pwm_static_wiring", "repeat_static_low_preflight_after_fix"],
        "active_pwm_allowed": False,
    }
    try:
        passed = sl.static_low_conclusion({"pass": True, "pattern": "all_pwm_low_safe"}, True)
        failed = sl.static_low_conclusion({"pass": False, "pattern": "low_side_static_high"}, True)
        actual = {
            "pass_result": passed.get("result"),
            "pass_next": passed.get("next_actions"),
            "fail_result": failed.get("result"),
            "fail_next": failed.get("next_actions"),
            "active_pwm_allowed": bool(passed.get("active_pwm_allowed") or failed.get("active_pwm_allowed")),
        }
        ok = actual == expected
        return CaseResult(
            "static_low_conclusion_classifies_next_debug_layer",
            ok,
            expected,
            actual,
            "" if ok else "diagnostic conclusion mismatch",
        )
    except Exception as exc:
        return CaseResult("static_low_conclusion_classifies_next_debug_layer", False, expected, {}, f"{type(exc).__name__}: {exc}")


def cases() -> list[CaseResult]:
    return [
        run_requires_hv_off_case(),
        run_dry_run_plans_restore_case(),
        run_success_restores_runtime_case(),
        run_restore_failure_overrides_success_case(),
        run_capture_command_failure_blocks_pass_case(),
        run_build_failure_does_not_restore_case(),
        run_static_low_conclusion_case(),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "bluepill_static_low_preflight_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
