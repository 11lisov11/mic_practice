#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_last_json_line(text: str) -> dict[str, Any] | None:
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def validate_payload(name: str, payload: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "missing JSON object payload"
    if name == "bench_gate_report":
        required = {"ready_for_active_pwm", "failed", "warnings", "failed_checks", "warning_checks", "summary", "next_actions"}
    elif name == "research_readiness_check":
        required = {"ready", "profile", "summary"}
    elif name == "current_bench_status_write":
        required = {"ready_for_active_pwm", "bench_summary", "readiness_summary", "build_only_summary", "next_actions", "out"}
    elif name == "current_bench_status_check":
        required = {
            "ready_for_active_pwm",
            "bench_summary",
            "readiness_summary",
            "build_only_summary",
            "next_actions",
            "out",
            "check_pass",
        }
    else:
        required = set()

    missing = sorted(key for key in required if key not in payload)
    if missing:
        return False, "missing key(s): " + ", ".join(missing)
    if "summary" in required and not str(payload.get("summary") or "").strip():
        return False, "summary path is empty"
    if "next_actions" in required and not isinstance(payload.get("next_actions"), list):
        return False, "next_actions must be a list"
    if name == "bench_gate_report":
        failed_checks = payload.get("failed_checks")
        warning_checks = payload.get("warning_checks")
        if not isinstance(failed_checks, list):
            return False, "failed_checks must be a list"
        if not isinstance(warning_checks, list):
            return False, "warning_checks must be a list"
        if not isinstance(payload.get("failed"), int) or payload.get("failed") != len(failed_checks):
            return False, "failed count does not match failed_checks"
        if not isinstance(payload.get("warnings"), int) or payload.get("warnings") != len(warning_checks):
            return False, "warnings count does not match warning_checks"
        if payload.get("ready_for_active_pwm") is True and failed_checks:
            return False, "ready gate cannot have failed_checks"
    if name == "current_bench_status_check" and payload.get("check_pass") is not True:
        return False, "current status check_pass is not true"
    return True, ""


def run_json_step(
    name: str,
    cmd: list[str],
    *,
    cwd: Path,
    timeout_s: float,
    accepted_returncodes: set[int],
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        payload = parse_last_json_line(proc.stdout)
        schema_ok, schema_detail = validate_payload(name, payload)
        ok = proc.returncode in accepted_returncodes and schema_ok
        return {
            "name": name,
            "cmd": cmd,
            "returncode": proc.returncode,
            "ok": ok,
            "schema_ok": schema_ok,
            "schema_detail": schema_detail,
            "payload": payload,
            "stdout_tail": "\n".join((proc.stdout or "").splitlines()[-8:]),
            "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-8:]),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "cmd": cmd,
            "returncode": None,
            "ok": False,
            "payload": None,
            "error": f"timeout after {exc.timeout}s",
            "stdout_tail": exc.stdout or "",
            "stderr_tail": exc.stderr or "",
        }
    except Exception as exc:
        return {
            "name": name,
            "cmd": cmd,
            "returncode": None,
            "ok": False,
            "payload": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def run_build_only_step(repo: Path, timeout_s: float) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-u",
        str(repo / "tools" / "full_system_preflight.py"),
        "--build-only",
        "--timeout-build",
        str(int(max(1.0, timeout_s))),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
        stdout_tail = "\n".join((proc.stdout or "").splitlines()[-12:])
        stderr_tail = "\n".join((proc.stderr or "").splitlines()[-12:])
        build_pass = "BUILD_ONLY_PASS=True" in (proc.stdout or "")
        return {
            "name": "full_system_preflight_build_only",
            "cmd": cmd,
            "returncode": proc.returncode,
            "ok": proc.returncode == 0 and build_pass,
            "build_only_pass": build_pass,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": "full_system_preflight_build_only",
            "cmd": cmd,
            "returncode": None,
            "ok": False,
            "build_only_pass": False,
            "error": f"timeout after {exc.timeout}s",
            "stdout_tail": exc.stdout or "",
            "stderr_tail": exc.stderr or "",
        }
    except Exception as exc:
        return {
            "name": "full_system_preflight_build_only",
            "cmd": cmd,
            "returncode": None,
            "ok": False,
            "build_only_pass": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def action_ids(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        return []
    out: list[str] = []
    for item in payload.get("next_actions", []):
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and item.get("id"):
            out.append(str(item["id"]))
    return out


def refresh_bench_status(
    repo: Path,
    url: str,
    profile: str,
    out: str,
    timeout_s: float,
    *,
    build_if_stale: bool = False,
    build_timeout_s: float = 300.0,
) -> dict[str, Any]:
    tools = repo / "tools"
    steps = []
    bench_step = run_json_step(
        "bench_gate_report",
        [sys.executable, "-u", str(tools / "bench_gate_report.py"), "--url", url],
        cwd=repo,
        timeout_s=timeout_s,
        accepted_returncodes={0, 1},
    )
    steps.append(bench_step)

    build_ran = False
    if build_if_stale and "run_full_build_only_preflight" in action_ids(bench_step.get("payload")):
        build_ran = True
        build_step = run_build_only_step(repo, build_timeout_s)
        steps.append(build_step)
        if build_step.get("ok"):
            steps.append(
                run_json_step(
                    "bench_gate_report_after_build",
                    [sys.executable, "-u", str(tools / "bench_gate_report.py"), "--url", url],
                    cwd=repo,
                    timeout_s=timeout_s,
                    accepted_returncodes={0, 1},
                )
            )

    steps.extend(
        [
            run_json_step(
                "research_readiness_check",
                [sys.executable, "-u", str(tools / "research_readiness_check.py"), "--profile", profile, "--url", url],
                cwd=repo,
                timeout_s=timeout_s,
                accepted_returncodes={0, 1, 4},
            ),
            run_json_step(
                "current_bench_status_write",
                [sys.executable, "-u", str(tools / "current_bench_status.py"), "--out", out],
                cwd=repo,
                timeout_s=timeout_s,
                accepted_returncodes={0},
            ),
            run_json_step(
                "current_bench_status_check",
                [sys.executable, "-u", str(tools / "current_bench_status.py"), "--out", out, "--check"],
                cwd=repo,
                timeout_s=timeout_s,
                accepted_returncodes={0},
            ),
        ]
    )

    required_ok = all(bool(step.get("ok")) for step in steps)
    check_payload = steps[-1].get("payload") if isinstance(steps[-1].get("payload"), dict) else {}
    ready = bool(check_payload.get("ready_for_active_pwm")) if isinstance(check_payload, dict) else False
    return {
        "tool": "refresh_bench_status",
        "pass": required_ok,
        "ready_for_active_pwm": ready,
        "build_if_stale": bool(build_if_stale),
        "build_ran": bool(build_ran),
        "current_status_check_pass": bool(check_payload.get("check_pass")) if isinstance(check_payload, dict) else False,
        "current_status": check_payload.get("out") if isinstance(check_payload, dict) else str((repo / out).resolve()),
        "bench_summary": check_payload.get("bench_summary") if isinstance(check_payload, dict) else None,
        "readiness_summary": check_payload.get("readiness_summary") if isinstance(check_payload, dict) else None,
        "build_only_summary": check_payload.get("build_only_summary") if isinstance(check_payload, dict) else None,
        "next_actions": check_payload.get("next_actions") if isinstance(check_payload, dict) else [],
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh bench gate, readiness summary, and root CURRENT_BENCH_STATUS_RU.md without active PWM."
    )
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--url", default="http://127.0.0.1:18080")
    parser.add_argument("--profile", default="bringup")
    parser.add_argument("--out", default="CURRENT_BENCH_STATUS_RU.md")
    parser.add_argument("--timeout-step", type=float, default=90.0)
    parser.add_argument("--build-if-stale", action="store_true", help="Run full_system_preflight.py --build-only if gate asks for it.")
    parser.add_argument("--build-timeout", type=float, default=300.0)
    parser.add_argument("--fail-if-not-ready", action="store_true", help="Return 1 when refresh succeeds but active PWM is not ready.")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    result = refresh_bench_status(
        repo,
        args.url,
        args.profile,
        args.out,
        float(args.timeout_step),
        build_if_stale=bool(args.build_if_stale),
        build_timeout_s=float(args.build_timeout),
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["pass"]:
        return 2
    if args.fail_if_not_ready and not result["ready_for_active_pwm"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
