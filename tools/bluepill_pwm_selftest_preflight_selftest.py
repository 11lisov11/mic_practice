#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import bluepill_pwm_selftest_preflight as ps


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    detail: str = ""


def latest_summary(out_root: Path) -> dict[str, Any]:
    summaries = sorted(out_root.glob("bluepill_pwm_selftest_preflight_*/summary.json"), key=lambda p: p.stat().st_mtime)
    if not summaries:
        raise AssertionError(f"no summary.json under {out_root}")
    return json.loads(summaries[-1].read_text(encoding="utf-8"))


class PatchScope:
    def __init__(self, **patches: Any) -> None:
        self.patches = patches
        self.old: dict[str, Any] = {}

    def __enter__(self) -> None:
        for name, value in self.patches.items():
            self.old[name] = getattr(ps, name)
            setattr(ps, name, value)

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        for name, value in self.old.items():
            setattr(ps, name, value)


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
            "bluepill_pwm_selftest_preflight.py",
            "--repo",
            str(Path(__file__).resolve().parents[1]),
            "--out-root",
            str(out_root),
            *args,
        ]
        with PatchScope(run_cmd=wrapped_run_cmd, collect_run_metadata=lambda repo: {"repo": str(repo)}):
            try:
                rc = ps.main()
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
        "error": "--confirm-hv-off is required before uploading self-test firmware",
        "calls": [],
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            rc, summary = run_main([], Path(tmp))
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
        "calls": ["build_selftest", "build_restore"],
        "selftest_env": "bluepill_pwm_selftest",
        "restore_env": "bluepill_uart_pwm",
        "restore_attempted": False,
        "has_upload_selftest": True,
        "has_upload_restore": True,
        "upload_selftest_uses_python_module_platformio": True,
        "restore_uses_python_module_platformio": True,
        "upload_selftest_uses_bare_pio": False,
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            rc, summary = run_main(["--dry-run"], Path(tmp))
            planned = summary.get("planned_commands", {}) if isinstance(summary.get("planned_commands"), dict) else {}
            upload_cmd = " ".join(str(x) for x in planned.get("upload_selftest", []))
            restore_cmd = " ".join(str(x) for x in planned.get("upload_restore", []))
            upload_parts = [str(x) for x in planned.get("upload_selftest", [])]
            restore_parts = [str(x) for x in planned.get("upload_restore", [])]
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "dry_run": summary.get("dry_run"),
                "calls": summary.get("_run_cmd_calls"),
                "selftest_env": summary.get("selftest_env"),
                "restore_env": summary.get("restore_env"),
                "restore_attempted": summary.get("restore_attempted"),
                "has_upload_selftest": "-e bluepill_pwm_selftest -t upload" in upload_cmd,
                "has_upload_restore": "-e bluepill_uart_pwm -t upload" in restore_cmd,
                "upload_selftest_uses_python_module_platformio": upload_parts[:3] == [sys.executable, "-m", "platformio"],
                "restore_uses_python_module_platformio": restore_parts[:3] == [sys.executable, "-m", "platformio"],
                "upload_selftest_uses_bare_pio": bool(upload_parts and upload_parts[0] == "pio"),
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
        "timing_resolution_pass": True,
        "calls": [
            "build_selftest",
            "build_restore",
            "upload_selftest",
            "saleae_capture",
            "analyze_pwm",
            "restore_uart_firmware",
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
                    return {"pass": True}
                return {
                    "csv": str(out_root / "digital.csv"),
                    "channels": list(range(7)),
                    "selected_rate": 24_000_000,
                }

            with PatchScope(
                latest_probe_summary=lambda run_dir: fake_probe,
                read_json=fake_read_json,
            ):
                rc, summary = run_main(["--confirm-hv-off"], out_root)
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "restored": summary.get("restored"),
                "restore_attempted": summary.get("restore_attempted"),
                "timing_resolution_pass": summary.get("timing_resolution_pass"),
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
        "error": "restore_uart_firmware failed",
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            fake_probe = out_root / "probe_summary.json"

            def fake_run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
                ok = step != "restore_uart_firmware"
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
                    return {"pass": True}
                return {
                    "csv": str(out_root / "digital.csv"),
                    "channels": list(range(7)),
                    "selected_rate": 24_000_000,
                }

            with PatchScope(latest_probe_summary=lambda run_dir: fake_probe, read_json=fake_read_json):
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


def run_build_failure_does_not_restore_case() -> CaseResult:
    expected = {
        "rc": 3,
        "pass": False,
        "diagnostic_upload_attempted": False,
        "restore_attempted": False,
        "restored": False,
        "error": "build_selftest failed",
        "calls": ["build_selftest"],
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)

            def fake_run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
                ok = step != "build_selftest"
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


def run_timing_resolution_failure_still_restores_case() -> CaseResult:
    expected = {
        "rc": 6,
        "pass": False,
        "restored": True,
        "restore_attempted": True,
        "timing_resolution_pass": False,
        "error_prefix": "Saleae timing resolution too coarse",
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            fake_probe = out_root / "probe_summary.json"

            def fake_read_json(path: Path | None) -> dict[str, Any] | None:
                if path is None:
                    return None
                if Path(path).name == "pwm_analysis.json":
                    return {"pass": True}
                return {
                    "csv": str(out_root / "digital.csv"),
                    "channels": list(range(7)),
                    "selected_rate": 500_000,
                }

            with PatchScope(latest_probe_summary=lambda run_dir: fake_probe, read_json=fake_read_json):
                rc, summary = run_main(["--confirm-hv-off"], out_root)
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "restored": summary.get("restored"),
                "restore_attempted": summary.get("restore_attempted"),
                "timing_resolution_pass": summary.get("timing_resolution_pass"),
                "error_prefix": str(summary.get("error", ""))[:35],
            }
            ok = actual == expected
            return CaseResult("timing_resolution_failure_still_restores_runtime", ok, expected, actual, "" if ok else "timing failure mismatch")
    except Exception as exc:
        return CaseResult("timing_resolution_failure_still_restores_runtime", False, expected, {}, f"{type(exc).__name__}: {exc}")


def run_capture_command_failure_blocks_pass_case() -> CaseResult:
    expected = {
        "rc": 5,
        "pass": False,
        "restored": True,
        "restore_attempted": True,
        "saleae_capture_ok": False,
        "error": "saleae_capture failed",
        "calls": [
            "build_selftest",
            "build_restore",
            "upload_selftest",
            "saleae_capture",
            "restore_uart_firmware",
        ],
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_root = Path(tmp)
            fake_probe = out_root / "probe_summary.json"

            def fake_run_cmd(cmd: list[str], cwd: Path, timeout_s: float, step: str) -> dict[str, Any]:
                ok = step != "saleae_capture"
                return {
                    "step": step,
                    "cmd": cmd,
                    "returncode": 0 if ok else 1,
                    "duration_s": 0.0,
                    "stdout": "",
                    "stderr": "" if ok else "capture timeout",
                    "ok": ok,
                }

            def fake_read_json(path: Path | None) -> dict[str, Any] | None:
                if path is None:
                    return None
                return {
                    "csv": str(out_root / "digital.csv"),
                    "channels": list(range(7)),
                    "selected_rate": 24_000_000,
                }

            with PatchScope(latest_probe_summary=lambda run_dir: fake_probe, read_json=fake_read_json):
                rc, summary = run_main(["--confirm-hv-off"], out_root, fake_run_cmd)
            actual = {
                "rc": rc,
                "pass": summary.get("pass"),
                "restored": summary.get("restored"),
                "restore_attempted": summary.get("restore_attempted"),
                "saleae_capture_ok": summary.get("saleae_capture_ok"),
                "error": summary.get("error"),
                "calls": summary.get("_run_cmd_calls"),
            }
            ok = actual == expected
            return CaseResult("capture_command_failure_blocks_pass", ok, expected, actual, "" if ok else "capture failure mismatch")
    except Exception as exc:
        return CaseResult("capture_command_failure_blocks_pass", False, expected, {}, f"{type(exc).__name__}: {exc}")


def cases() -> list[CaseResult]:
    return [
        run_requires_hv_off_case(),
        run_dry_run_plans_restore_case(),
        run_success_restores_runtime_case(),
        run_restore_failure_overrides_success_case(),
        run_build_failure_does_not_restore_case(),
        run_timing_resolution_failure_still_restores_case(),
        run_capture_command_failure_blocks_pass_case(),
    ]


def main() -> int:
    results = cases()
    failed = [case for case in results if not case.ok]
    summary = {
        "tool": "bluepill_pwm_selftest_preflight_selftest",
        "pass": not failed,
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "cases": [case.__dict__ for case in results],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
