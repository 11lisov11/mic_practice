#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError

from run_metadata import collect_run_metadata, collect_source_fingerprint


SELFTEST_STEP_NAMES = tuple(sorted(path.stem for path in Path(__file__).resolve().parent.glob("*_selftest.py")))

BUILD_ONLY_STEP_NAMES = (
    "py_compile",
    "firmware_config_safety_check",
    "platformio_env_safety_check",
    "protocol_contract_check",
    "start_guard_static_check",
    *SELFTEST_STEP_NAMES,
    "unoq_build",
    "bluepill_build",
    "nucleo_build",
)


def select_required_steps(steps: list[dict], required_names: tuple[str, ...] = BUILD_ONLY_STEP_NAMES) -> list[dict]:
    required = set(required_names)
    return [step for step in steps if step.get("name") in required]


def audit_required_steps(steps: list[dict], required_names: tuple[str, ...] = BUILD_ONLY_STEP_NAMES) -> dict:
    required = tuple(required_names)
    required_set = set(required)
    counts = {name: 0 for name in required}
    failed: set[str] = set()
    for step in steps:
        name = str(step.get("name", ""))
        if name not in required_set:
            continue
        counts[name] = counts.get(name, 0) + 1
        if not step.get("ok"):
            failed.add(name)
    missing = [name for name in required if counts.get(name, 0) == 0]
    duplicates = [name for name in required if counts.get(name, 0) > 1]
    return {
        "pass": not missing and not failed and not duplicates,
        "required_count": len(required),
        "present_count": sum(1 for name in required if counts.get(name, 0) > 0),
        "missing": missing,
        "failed": sorted(failed),
        "duplicates": duplicates,
    }


def log(msg: str) -> None:
    print(msg, flush=True)


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def run_step(
    name: str,
    cmd: list[str],
    workdir: str,
    log_path: Path,
    timeout_s: float,
) -> dict:
    start = time.monotonic()
    log(f"RUN[{name}] {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    elapsed_s = time.monotonic() - start
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    log_path.write_text(stdout + ("\n[stderr]\n" + stderr if stderr else ""), encoding="utf-8")
    result = {
        "name": name,
        "cmd": cmd,
        "cwd": workdir,
        "rc": proc.returncode,
        "elapsed_s": elapsed_s,
        "ok": proc.returncode == 0,
        "log": str(log_path),
    }
    log(f"DONE[{name}] rc={proc.returncode} dt={elapsed_s:.2f}s log={log_path}")
    return result


def http_json(url: str, timeout_s: float) -> dict | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def http_post_json(url: str, payload: dict, timeout_s: float) -> dict | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError):
        return None


def get_status(base: str, timeout_s: float = 2.0) -> dict | None:
    resp = http_json(base.rstrip("/") + "/api/status", timeout_s)
    if not resp or not resp.get("ok"):
        return None
    return resp.get("data")


def status_num(st: dict, key: str, default: float = 0.0) -> float:
    try:
        val = st.get(key, default)
        if isinstance(val, str):
            val = val.strip()
        num = float(val)
        if not math.isfinite(num):
            return float(default)
        return num
    except Exception:
        return float(default)


def bp_link_live(st: dict | None, max_age_ms: float = 1000.0) -> bool:
    if st is None:
        return False
    if st.get("link") is False:
        return False
    ages: list[float] = []
    for key in ("bp_rsp_age_ms", "bp_age_ms"):
        if key in st:
            ages.append(status_num(st, key, 999999.0))
    if st.get("last_rx_age_s") is not None:
        ages.append(status_num(st, "last_rx_age_s", 999999.0) * 1000.0)
    return bool(ages) and min(ages) <= max_age_ms


def status_is_safe(st: dict | None) -> bool:
    if st is None:
        return False
    bp_bad_values = [int(status_num(st, key, 999999.0)) for key in ("bp_bad_cnt", "bp_bad") if key in st]
    bp_bad = max(bp_bad_values) if bp_bad_values else 999999
    return (
        int(status_num(st, "pwm", 1.0)) == 0
        and int(status_num(st, "estop", 1.0)) == 0
        and st.get("state") == "SAFE"
        and bp_link_live(st)
        and int(status_num(st, "bp_fault", 255.0)) == 0
        and bp_bad == 0
    )


def safe_stop_http(base: str, attempts: int = 3) -> bool:
    base = base.rstrip("/")
    for _ in range(max(1, attempts)):
        http_post_json(base + "/api/cmd", {"cmd": "STOP"}, 1.5)
        http_post_json(base + "/api/cmd", {"cmd": "CLEAR"}, 1.5)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            st = get_status(base, timeout_s=1.0)
            if status_is_safe(st):
                return True
            time.sleep(0.15)
    return False


def latest_json(path: Path) -> Path | None:
    files = sorted(path.rglob("summary.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def classify_mic_compare(summary: dict) -> dict:
    if summary.get("pass") is True:
        return {"status": "pass", "reason": "mic_compare_pass"}
    mic = summary.get("mic", {}) if isinstance(summary.get("mic"), dict) else {}
    link_flags = mic.get("mic_link_flags_values") or []
    status_flags = mic.get("mic_status_flags_values") or []
    gated_ratio = float(mic.get("mic_gated_ratio") or 0.0)
    enable_ratio = float(mic.get("mic_enable_ai_ratio") or 0.0)
    speed_err_hz = mic.get("mean_mic_speed_err_hz")
    speed_tol_hz = mic.get("mean_mic_speed_tol_hz")
    enc_used_values = mic.get("mic_enc_used_values") or []
    stationary_gate = (
        gated_ratio >= 0.9
        and enable_ratio == 0.0
        and link_flags == [0]
        and status_flags == [0]
        and enc_used_values in ([0], [1])
        and speed_err_hz is not None
        and speed_tol_hz is not None
        and float(speed_err_hz) > max(1.0, float(speed_tol_hz) * 2.0)
    )
    if stationary_gate:
        return {
            "status": "diagnostic_only",
            "reason": "mic_correctly_gated_by_measured_speed",
        }
    return {"status": "fail", "reason": "mic_compare_thresholds_failed"}


def read_json(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_result_summary(result: dict, out_path: Path) -> None:
    summary = result.get("summary")
    if isinstance(summary, dict):
        for key, value in summary.items():
            result[key] = value
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def recover_ui(
    repo_root: Path,
    base_url: str,
    forward_port: int,
    logs_dir: Path,
    result_steps: list[dict],
) -> dict:
    info = run_step(
        "ui_access_recover",
        [sys.executable, "tools\\ui_access.py", "--forward-port", str(forward_port)],
        str(repo_root),
        logs_dir / "ui_access_recover.log",
        90.0,
    )
    result_steps.append(info)
    if get_status(base_url, timeout_s=1.5) is not None:
        return info
    restart = run_step(
        "web_hmi_restart",
        [sys.executable, "tools\\adb_deploy_web_hmi.py", "--restart"],
        str(repo_root),
        logs_dir / "web_hmi_restart.log",
        180.0,
    )
    result_steps.append(restart)
    info2 = run_step(
        "ui_access_recover_after_restart",
        [sys.executable, "tools\\ui_access.py", "--forward-port", str(forward_port)],
        str(repo_root),
        logs_dir / "ui_access_recover_after_restart.log",
        90.0,
    )
    result_steps.append(info2)
    return info2


def stabilize_ui_phase(
    repo_root: Path,
    base_url: str,
    forward_port: int,
    logs_dir: Path,
    result_steps: list[dict],
    phase_tag: str,
    require_safe: bool = True,
    settle_s: float = 0.5,
) -> dict | None:
    info = run_step(
        f"{phase_tag}_ui_access",
        [sys.executable, "tools\\ui_access.py", "--forward-port", str(forward_port)],
        str(repo_root),
        logs_dir / f"{phase_tag}_ui_access.log",
        90.0,
    )
    result_steps.append(info)
    st = get_status(base_url, timeout_s=1.5)
    if st is None:
        recover_ui(repo_root, base_url, forward_port, logs_dir, result_steps)
        st = get_status(base_url, timeout_s=1.5)
    if require_safe and not status_is_safe(st):
        safe_stop_http(base_url, attempts=4)
        st = get_status(base_url, timeout_s=1.5)
        if st is None or not status_is_safe(st):
            recover_ui(repo_root, base_url, forward_port, logs_dir, result_steps)
            safe_stop_http(base_url, attempts=4)
            st = get_status(base_url, timeout_s=1.5)
    if settle_s > 0:
        time.sleep(settle_s)
    return st


def main() -> int:
    ap = argparse.ArgumentParser(description="Build + HIL regression runner for the full UNO Q / Blue Pill project.")
    ap.add_argument("--url", default="http://127.0.0.1:18080")
    ap.add_argument("--forward-port", type=int, default=18080)
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "_preflight_exports"))
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--build-only", action="store_true", help="Run only compile/build/offline protocol checks; do not touch HMI, UART, Saleae, or PWM.")
    ap.add_argument("--skip-hil", action="store_true")
    ap.add_argument("--skip-full-suite", action="store_true")
    ap.add_argument(
        "--full-suite-capture-every-hz",
        type=float,
        default=1.0,
        help="Additional Saleae capture interval; use 0 for key frequencies only.",
    )
    ap.add_argument("--skip-mic-compare", action="store_true")
    ap.add_argument("--with-fan", action="store_true", help="Run optional low-voltage fan PWM/tach preflight.")
    ap.add_argument("--fan-duties", default="0,0.3,0.6,1.0,0")
    ap.add_argument("--fan-require-tach", action="store_true", help="Require fan tach pulses during fan preflight.")
    ap.add_argument("--fan-max-vdc", type=float, default=60.0)
    ap.add_argument("--fan-allow-hv", action="store_true", help="Allow fan preflight when Vbus is above --fan-max-vdc.")
    ap.add_argument("--with-bpfoc", action="store_true", help="Run optional low-voltage Blue Pill measured-angle FOC backend preflight.")
    ap.add_argument("--bpfoc-freq", type=float, default=1.0)
    ap.add_argument("--bpfoc-max-vdc", type=float, default=60.0)
    ap.add_argument("--bpfoc-allow-hv", action="store_true", help="Allow BPFOC preflight when Vbus is above --bpfoc-max-vdc.")
    ap.add_argument("--bpfoc-allow-no-encoder", action="store_true", help="Do not require enc_ok=1 for BPFOC preflight.")
    ap.add_argument("--with-bluepill-pwm-selftest", action="store_true", help="Run ST-Link Blue Pill PWM self-test + Saleae capture before HMI tests.")
    ap.add_argument("--confirm-hv-off", action="store_true", help="Required for firmware-swapping self-test stages: HV bus is disconnected and discharged.")
    ap.add_argument("--bp-pwm-selftest-rate", type=int, default=6_000_000)
    ap.add_argument("--bp-pwm-selftest-duration", type=float, default=4.0)
    ap.add_argument("--bp-pwm-selftest-no-auto-rate", action="store_true")
    ap.add_argument("--with-hv", action="store_true", help="Run optional HV/J7 preflight after low-voltage HIL has passed.")
    ap.add_argument("--hv-vf-freqs", default="0.5,1,2,5")
    ap.add_argument("--hv-estop-freqs", default="1,5")
    ap.add_argument("--hv-vdc-min", type=float, default=None, help="Optional lower bound for board-scaled vdc during HV/J7 preflight.")
    ap.add_argument("--hv-vdc-max", type=float, default=None, help="Optional upper bound for board-scaled vdc during HV/J7 preflight.")
    ap.add_argument("--encoder-duration", type=float, default=3.0)
    ap.add_argument("--timeout-build", type=float, default=300.0)
    ap.add_argument("--timeout-step", type=float, default=900.0)
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    run_dir = Path(args.outdir).resolve() / f"full_system_preflight_{ts_tag()}"
    logs_dir = run_dir / "logs"
    scalar_dir = run_dir / "scalar"
    foc_dir = run_dir / "foc_mic"
    la_dir = run_dir / "full_suite"
    mic_dir = run_dir / "mic_compare"
    fan_dir = run_dir / "fan"
    bpfoc_dir = run_dir / "bpfoc"
    bp_pwm_selftest_dir = run_dir / "bluepill_pwm_selftest"
    hv_dir = run_dir / "hv_j7"
    logs_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "ts": run_dir.name.rsplit("_", 1)[-1],
        "base_url": args.url.rstrip("/"),
        "run_dir": str(run_dir),
        "run_metadata": collect_run_metadata(repo_root),
        "source_fingerprint": collect_source_fingerprint(repo_root),
        "steps": [],
    }

    def step(name: str, cmd: list[str], workdir: Path, timeout_s: float) -> dict:
        info = run_step(name, cmd, str(workdir), logs_dir / f"{name}.log", timeout_s)
        result["steps"].append(info)
        return info

    try:
        if not args.skip_build:
            py_compile_targets = sorted(
                str(path.relative_to(repo_root))
                for path in (repo_root / "tools").glob("*.py")
                if path.is_file()
            )
            py_compile_targets.extend(
                sorted(
                    str(path.relative_to(repo_root))
                    for path in (repo_root / "motor_identification").glob("*.py")
                    if path.is_file()
                )
            )
            py_compile_targets.append("web_hmi\\server.py")
            step(
                "py_compile",
                [sys.executable, "-m", "py_compile", *py_compile_targets],
                repo_root,
                args.timeout_build,
            )
            step(
                "firmware_config_safety_check",
                [sys.executable, "-u", "tools\\firmware_config_safety_check.py"],
                repo_root,
                60.0,
            )
            step(
                "platformio_env_safety_check",
                [sys.executable, "-u", "tools\\platformio_env_safety_check.py"],
                repo_root,
                60.0,
            )
            step(
                "protocol_contract_check",
                [sys.executable, "-u", "tools\\protocol_contract_check.py"],
                repo_root,
                60.0,
            )
            step(
                "protocol_safety_selftest",
                [sys.executable, "-u", "tools\\protocol_safety_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "pc_direct_hmi_selftest",
                [sys.executable, "-u", "tools\\pc_direct_hmi_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "pc_direct_hmi_service_selftest",
                [sys.executable, "-u", "tools\\pc_direct_hmi_service_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "web_hmi_command_guard_selftest",
                [sys.executable, "-u", "tools\\web_hmi_command_guard_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "ui_pwm_case_selftest",
                [sys.executable, "-u", "tools\\ui_pwm_case_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "dense_overlap_sweep_selftest",
                [sys.executable, "-u", "tools\\dense_overlap_sweep_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "bluepill_uart_diagnose_selftest",
                [sys.executable, "-u", "tools\\bluepill_uart_diagnose_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "uart_loopback_preflight_selftest",
                [sys.executable, "-u", "tools\\uart_loopback_preflight_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "adb_router_sequence_selftest",
                [sys.executable, "-u", "tools\\adb_router_sequence_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "adb_deploy_web_hmi_selftest",
                [sys.executable, "-u", "tools\\adb_deploy_web_hmi_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "active_pwm_guard_selftest",
                [sys.executable, "-u", "tools\\active_pwm_guard_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "fan_preflight_selftest",
                [sys.executable, "-u", "tools\\fan_preflight_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "bpfoc_backend_preflight_selftest",
                [sys.executable, "-u", "tools\\bpfoc_backend_preflight_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "mic_ai_compare_selftest",
                [sys.executable, "-u", "tools\\mic_ai_compare_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "hv_j7_preflight_selftest",
                [sys.executable, "-u", "tools\\hv_j7_preflight_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "bluepill_runtime_static_preflight_selftest",
                [sys.executable, "-u", "tools\\bluepill_runtime_static_preflight_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "bluepill_static_low_preflight_selftest",
                [sys.executable, "-u", "tools\\bluepill_static_low_preflight_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "bluepill_pwm_selftest_preflight_selftest",
                [sys.executable, "-u", "tools\\bluepill_pwm_selftest_preflight_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "bench_gate_report_selftest",
                [sys.executable, "-u", "tools\\bench_gate_report_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "current_bench_status_selftest",
                [sys.executable, "-u", "tools\\current_bench_status_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "refresh_bench_status_selftest",
                [sys.executable, "-u", "tools\\refresh_bench_status_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "research_readiness_check_selftest",
                [sys.executable, "-u", "tools\\research_readiness_check_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "start_guard_static_check",
                [sys.executable, "-u", "tools\\start_guard_static_check.py"],
                repo_root,
                60.0,
            )
            step(
                "start_guard_static_check_selftest",
                [sys.executable, "-u", "tools\\start_guard_static_check_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "saleae_highlevel_probe_selftest",
                [sys.executable, "-u", "tools\\saleae_highlevel_probe_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "saleae_pwm_analyze_selftest",
                [sys.executable, "-u", "tools\\saleae_pwm_analyze_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "runtime_python_selftest",
                [sys.executable, "-u", "tools\\runtime_python_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "run_metadata_selftest",
                [sys.executable, "-u", "tools\\run_metadata_selftest.py"],
                repo_root,
                60.0,
            )
            step(
                "full_system_preflight_selftest",
                [sys.executable, "-u", "tools\\full_system_preflight_selftest.py"],
                repo_root,
                60.0,
            )

            # Keep the release gate complete when a new standalone self-test is added.
            completed_step_names = {item["name"] for item in result["steps"]}
            for selftest_name in SELFTEST_STEP_NAMES:
                if selftest_name in completed_step_names:
                    continue
                step(
                    selftest_name,
                    [sys.executable, "-u", f"tools\\{selftest_name}.py"],
                    repo_root,
                    60.0,
                )
            step(
                "unoq_build",
                ["arduino-cli", "compile", "--fqbn", "arduino:zephyr:unoq:link_mode=static", ".\\UNOQ_MOTOR"],
                repo_root,
                args.timeout_build,
            )
            step(
                "bluepill_build",
                [sys.executable, "-m", "platformio", "run"],
                repo_root / "bluepill_uart_pwm_pio",
                args.timeout_build,
            )
            step(
                "nucleo_build",
                [
                    sys.executable,
                    "-m",
                    "platformio",
                    "run",
                    "-e",
                    "nucleo_g431_uart_bridge",
                    "-e",
                    "nucleo_g431_pwm_bench",
                ],
                repo_root / "nucleo_g431_uart_bridge_pio",
                args.timeout_build,
            )

        if args.build_only:
            build_steps = select_required_steps(result["steps"])
            build_audit = audit_required_steps(result["steps"])
            build_only_pass = bool(build_steps) and bool(build_audit["pass"])
            result["summary"] = {
                "build_only": True,
                "build_only_pass": build_only_pass,
                "build_pass": build_only_pass,
                "build_step_audit": build_audit,
                "required_hil_pass": False,
                "full_suite_pass": False,
                "precharge_relay_stage_enabled": False,
                "precharge_relay_pass": None,
                "precharge_relay_saleae_enabled": False,
                "precharge_relay_saleae_pass": None,
                "fan_stage_enabled": False,
                "fan_pass": None,
                "bpfoc_stage_enabled": False,
                "bpfoc_pass": None,
                "bluepill_pwm_selftest_stage_enabled": False,
                "bluepill_pwm_selftest_pass": None,
                "hv_stage_enabled": False,
                "hv_pass": None,
                "mic_compare_status": "not_run_build_only",
                "final_safe": None,
                "overall_pass": False,
            }
            out_path = run_dir / "summary.json"
            write_result_summary(result, out_path)
            log(f"SUMMARY: {out_path}")
            log(f"BUILD_ONLY_PASS={build_only_pass}")
            return 0 if build_only_pass else 4

        if args.with_bluepill_pwm_selftest and not args.skip_hil:
            bp_selftest_cmd = [
                sys.executable,
                "-u",
                "tools\\bluepill_pwm_selftest_preflight.py",
                "--rate",
                str(int(args.bp_pwm_selftest_rate)),
                "--duration",
                f"{float(args.bp_pwm_selftest_duration):.3f}",
                "--out-root",
                str(bp_pwm_selftest_dir),
            ]
            if args.confirm_hv_off:
                bp_selftest_cmd.append("--confirm-hv-off")
            if args.bp_pwm_selftest_no_auto_rate:
                bp_selftest_cmd.append("--no-auto-rate")
            step("bluepill_pwm_selftest_preflight", bp_selftest_cmd, repo_root, args.timeout_step)

        access = step(
            "ui_access",
            [sys.executable, "tools\\ui_access.py", "--forward-port", str(args.forward_port)],
            repo_root,
            90.0,
        )
        status_before = get_status(args.url)
        if not access["ok"] or status_before is None:
            recover_ui(repo_root, args.url, args.forward_port, logs_dir, result["steps"])
            status_before = get_status(args.url, timeout_s=1.5)
        result["status_before"] = status_before

        logic_ready = True
        if not args.skip_hil and status_before is not None:
            logic = step(
                "logic2_recover",
                [sys.executable, "tools\\logic2_recover.py"],
                repo_root,
                90.0,
            )
            if not logic["ok"]:
                logic = step(
                    "logic2_recover_restart",
                    [sys.executable, "tools\\logic2_recover.py", "--restart", "--wait-app", "30", "--wait-device", "30"],
                    repo_root,
                    120.0,
                )
            logic_ready = logic["ok"]
            step(
                "encoder_test",
                [
                    sys.executable,
                    "tools\\encoder_test.py",
                    "--url",
                    args.url,
                    "--duration",
                    str(args.encoder_duration),
                    "--poll",
                    "0.05",
                ],
                repo_root,
                120.0,
            )
            if args.with_fan:
                stabilize_ui_phase(
                    repo_root,
                    args.url,
                    args.forward_port,
                    logs_dir,
                    result["steps"],
                    phase_tag="pre_fan",
                    require_safe=True,
                    settle_s=0.5,
                )
                fan_cmd = [
                    sys.executable,
                    "-u",
                    "tools\\fan_preflight.py",
                    "--url",
                    args.url,
                    "--duties",
                    args.fan_duties,
                    "--max-vdc",
                    f"{float(args.fan_max_vdc):.2f}",
                    "--out-root",
                    str(fan_dir),
                ]
                if args.fan_require_tach:
                    fan_cmd.append("--require-tach")
                if args.fan_allow_hv:
                    fan_cmd.append("--allow-hv")
                step("fan_preflight", fan_cmd, repo_root, 180.0)

            if args.with_bpfoc:
                stabilize_ui_phase(
                    repo_root,
                    args.url,
                    args.forward_port,
                    logs_dir,
                    result["steps"],
                    phase_tag="pre_bpfoc",
                    require_safe=True,
                    settle_s=0.5,
                )
                bpfoc_cmd = [
                    sys.executable,
                    "-u",
                    "tools\\bpfoc_backend_preflight.py",
                    "--url",
                    args.url,
                    "--freq",
                    f"{float(args.bpfoc_freq):.2f}",
                    "--max-vdc",
                    f"{float(args.bpfoc_max_vdc):.2f}",
                    "--out-root",
                    str(bpfoc_dir),
                ]
                if args.bpfoc_allow_hv:
                    bpfoc_cmd.append("--allow-hv")
                if args.bpfoc_allow_no_encoder:
                    bpfoc_cmd.append("--allow-no-encoder")
                step("bpfoc_backend_preflight", bpfoc_cmd, repo_root, 180.0)

            if logic_ready:
                step(
                    "scalar_vf_preflight",
                    [
                        sys.executable,
                        "-u",
                        "tools\\scalar_vf_preflight.py",
                        "--url",
                        args.url,
                        "--freqs",
                        "0.1,0.5,1,2,5,10,20,30,40,50",
                        "--estop-freqs",
                        "0.5,10,50",
                        "--la-channels",
                        "0,1,2,3,4,5,6",
                        "--la-rate",
                        "24000000",
                        "--la-duration",
                        "0.003",
                        "--min-handoff-gap-ns",
                        "600",
                        "--outdir",
                        str(scalar_dir),
                    ],
                    repo_root,
                    args.timeout_step,
                )
                step(
                    "foc_mic_preflight",
                    [
                        sys.executable,
                        "-u",
                        "tools\\foc_mic_preflight.py",
                        "--url",
                        args.url,
                        "--foc-freqs",
                        "0.5,5,10,20,50",
                        "--foc-estop-freqs",
                        "10,50",
                        "--mic-freqs",
                        "5,10,20",
                        "--la-channels",
                        "0,1,2,3,4,5,6",
                        "--la-rate",
                        "24000000",
                        "--la-duration",
                        "0.003",
                        "--min-handoff-gap-ns",
                        "600",
                        "--outdir",
                        str(foc_dir),
                    ],
                    repo_root,
                    args.timeout_step,
                )

                if not args.skip_full_suite:
                    stabilize_ui_phase(
                        repo_root,
                        args.url,
                        args.forward_port,
                        logs_dir,
                        result["steps"],
                        phase_tag="pre_full_suite",
                        require_safe=True,
                        settle_s=0.5,
                    )
                    step(
                        "ui_pwm_suite",
                        [
                            sys.executable,
                            "-u",
                            "tools\\ui_pwm_suite.py",
                            "--url",
                            args.url,
                            "--capture-every-hz",
                            str(max(0.0, args.full_suite_capture_every_hz)),
                            "--la-channels",
                            "0,1,2,3,4,5,6",
                            "--la-rate",
                            "24000000",
                            "--la-duration",
                            "0.06",
                            "--case-retries",
                            "2",
                            "--retry-delay",
                            "0.2",
                            "--min-handoff-gap-ns",
                            "600",
                            "--outdir",
                            str(la_dir),
                        ],
                        repo_root,
                        args.timeout_step,
                    )

                if args.with_hv:
                    stabilize_ui_phase(
                        repo_root,
                        args.url,
                        args.forward_port,
                        logs_dir,
                        result["steps"],
                        phase_tag="pre_hv_j7",
                        require_safe=True,
                        settle_s=1.0,
                    )
                    hv_cmd = [
                        sys.executable,
                        "-u",
                        "tools\\hv_j7_preflight.py",
                        "--url",
                        args.url,
                        "--vf-freqs",
                        args.hv_vf_freqs,
                        "--estop-freqs",
                        args.hv_estop_freqs,
                        "--la-channels",
                        "0,1,2,3,4,5,6",
                        "--la-rate",
                        "24000000",
                        "--la-duration",
                        "0.02",
                        "--cmd-retries",
                        "2",
                        "--case-retries",
                        "1",
                        "--retry-delay",
                        "0.2",
                        "--settle",
                        "0.5",
                        "--min-handoff-gap-ns",
                        "600",
                        "--outdir",
                        str(hv_dir),
                    ]
                    if args.hv_vdc_min is not None:
                        hv_cmd += ["--vdc-min", str(args.hv_vdc_min)]
                    if args.hv_vdc_max is not None:
                        hv_cmd += ["--vdc-max", str(args.hv_vdc_max)]
                    step("hv_j7_preflight", hv_cmd, repo_root, args.timeout_step)

            if not args.skip_mic_compare:
                stabilize_ui_phase(
                    repo_root,
                    args.url,
                    args.forward_port,
                    logs_dir,
                    result["steps"],
                    phase_tag="pre_mic_compare",
                    require_safe=True,
                    settle_s=1.0,
                )
                step(
                    "mic_ai_compare",
                    [
                        sys.executable,
                        "-u",
                        "tools\\mic_ai_compare.py",
                        "--url",
                        args.url,
                        "--freq",
                        "10.0",
                        "--duration",
                        "3",
                        "--poll",
                        "0.05",
                        "--warmup",
                        "1.0",
                        "--mode-retries",
                        "1",
                        "--cmd-retries",
                        "2",
                        "--cmd-retry-delay",
                        "0.2",
                        "--settle",
                        "0.5",
                        "--tag",
                        "full_preflight_mic_compare",
                        "--outdir",
                        str(mic_dir),
                    ],
                    repo_root,
                    args.timeout_step,
                )

        result["scalar_summary"] = read_json(latest_json(scalar_dir))
        result["foc_mic_summary"] = read_json(latest_json(foc_dir))
        result["fan_summary"] = read_json(latest_json(fan_dir))
        result["bpfoc_summary"] = read_json(latest_json(bpfoc_dir))
        result["bluepill_pwm_selftest_summary"] = read_json(latest_json(bp_pwm_selftest_dir))
        result["hv_summary"] = read_json(latest_json(hv_dir))
        result["mic_compare_summary"] = read_json(latest_json(mic_dir))

        suite_csv = la_dir / "summary.csv"
        result["full_suite_summary_csv"] = str(suite_csv) if suite_csv.exists() else None
        if suite_csv.exists():
            pass_count = 0
            fail_count = 0
            with suite_csv.open("r", newline="", encoding="utf-8", errors="replace") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    pass_value = str(row.get("pass", "")).strip().lower()
                    if pass_value in ("true", "pass", "1", "yes"):
                        pass_count += 1
                    else:
                        fail_count += 1
            result["full_suite_pass_count"] = pass_count
            result["full_suite_fail_count"] = fail_count

        ui_pwm_suite_step = next((s for s in result["steps"] if s["name"] == "ui_pwm_suite"), None)
        mic_compare_step = next((s for s in result["steps"] if s["name"] == "mic_ai_compare"), None)
        if result["mic_compare_summary"] is not None:
            result["mic_compare_classification"] = classify_mic_compare(result["mic_compare_summary"])
        elif args.skip_mic_compare:
            result["mic_compare_classification"] = {"status": "skipped", "reason": "mic_compare_skipped"}
        elif mic_compare_step is not None and not mic_compare_step["ok"]:
            result["mic_compare_classification"] = {"status": "transport_fail", "reason": "mic_compare_did_not_complete"}
        else:
            result["mic_compare_classification"] = {"status": "fail", "reason": "mic_compare_thresholds_failed"}

        status_after = get_status(args.url, timeout_s=1.5)
        if status_after is None:
            recover_ui(repo_root, args.url, args.forward_port, logs_dir, result["steps"])
            status_after = get_status(args.url, timeout_s=1.5)
        if status_after is not None and not status_is_safe(status_after):
            safe_stop_http(args.url, attempts=4)
            status_after = get_status(args.url, timeout_s=1.5)
        elif status_after is None:
            recover_ui(repo_root, args.url, args.forward_port, logs_dir, result["steps"])
            safe_stop_http(args.url, attempts=4)
            status_after = get_status(args.url, timeout_s=1.5)
        result["status_after"] = status_after

        build_steps = select_required_steps(result["steps"])
        build_audit = audit_required_steps(result["steps"])
        required_hil = [
            s
            for s in result["steps"]
            if s["name"] in ("ui_access", "encoder_test", "scalar_vf_preflight", "foc_mic_preflight")
        ]
        if args.with_fan:
            required_hil += [s for s in result["steps"] if s["name"] == "fan_preflight"]
        if args.with_bpfoc:
            required_hil += [s for s in result["steps"] if s["name"] == "bpfoc_backend_preflight"]
        if args.with_bluepill_pwm_selftest and not args.skip_hil:
            required_hil += [s for s in result["steps"] if s["name"] == "bluepill_pwm_selftest_preflight"]
        if args.with_hv:
            required_hil += [s for s in result["steps"] if s["name"] == "hv_j7_preflight"]
        logic_steps = [s for s in result["steps"] if s["name"] in ("logic2_recover", "logic2_recover_restart")]
        logic_ok = any(s["ok"] for s in logic_steps) if logic_steps else True
        if not args.skip_full_suite:
            required_hil += [s for s in result["steps"] if s["name"] == "ui_pwm_suite"]

        full_suite_pass = True
        if not args.skip_full_suite:
            full_suite_pass = bool(
                ui_pwm_suite_step is not None
                and ui_pwm_suite_step["ok"]
                and suite_csv.exists()
                and result.get("full_suite_pass_count", 0) > 0
                and result.get("full_suite_fail_count", 0) == 0
            )

        fan_stage_pass = True if not args.with_fan else bool((result["fan_summary"] or {}).get("pass") is True)
        bpfoc_stage_pass = True if not args.with_bpfoc else bool((result["bpfoc_summary"] or {}).get("pass") is True)
        bp_pwm_selftest_stage_pass = True
        if args.with_bluepill_pwm_selftest and not args.skip_hil:
            bp_pwm_selftest_stage_pass = bool((result["bluepill_pwm_selftest_summary"] or {}).get("pass") is True)
        hv_stage_pass = True if not args.with_hv else bool((result["hv_summary"] or {}).get("pass") is True)

        result["summary"] = {
            "build_pass": bool(build_steps) and bool(build_audit["pass"]),
            "build_step_audit": build_audit,
            "required_hil_pass": (all(s["ok"] for s in required_hil) if required_hil else True) and logic_ok,
            "full_suite_pass": full_suite_pass,
            "precharge_relay_stage_enabled": False,
            "precharge_relay_pass": None,
            "precharge_relay_saleae_enabled": False,
            "precharge_relay_saleae_pass": None,
            "fan_stage_enabled": bool(args.with_fan),
            "fan_pass": fan_stage_pass if args.with_fan else None,
            "bpfoc_stage_enabled": bool(args.with_bpfoc),
            "bpfoc_pass": bpfoc_stage_pass if args.with_bpfoc else None,
            "bluepill_pwm_selftest_stage_enabled": bool(args.with_bluepill_pwm_selftest and not args.skip_hil),
            "bluepill_pwm_selftest_pass": bp_pwm_selftest_stage_pass if args.with_bluepill_pwm_selftest and not args.skip_hil else None,
            "hv_stage_enabled": bool(args.with_hv),
            "hv_pass": hv_stage_pass if args.with_hv else None,
            "mic_compare_status": result["mic_compare_classification"]["status"] if not args.skip_mic_compare else "skipped",
            "final_safe": status_is_safe(status_after),
        }
        result["summary"]["overall_pass"] = bool(
            result["summary"]["build_pass"]
            and result["summary"]["required_hil_pass"]
            and result["summary"]["full_suite_pass"]
            and fan_stage_pass
            and bpfoc_stage_pass
            and bp_pwm_selftest_stage_pass
            and hv_stage_pass
            and result["summary"]["final_safe"]
        )

        out_path = run_dir / "summary.json"
        write_result_summary(result, out_path)
        log(f"SUMMARY: {out_path}")
        log(f"PASS={result['summary']['overall_pass']}")
        return 0 if result["summary"]["overall_pass"] else 4
    except subprocess.TimeoutExpired as exc:
        result["timeout"] = {
            "cmd": exc.cmd,
            "timeout_s": exc.timeout,
        }
        result["summary"] = {
            "build_only": bool(args.build_only),
            "build_only_pass": False if args.build_only else None,
            "build_pass": False,
            "required_hil_pass": False,
            "full_suite_pass": False,
            "precharge_relay_stage_enabled": False,
            "precharge_relay_pass": None,
            "precharge_relay_saleae_enabled": False,
            "precharge_relay_saleae_pass": None,
            "fan_stage_enabled": bool(args.with_fan),
            "fan_pass": None,
            "bpfoc_stage_enabled": bool(args.with_bpfoc),
            "bpfoc_pass": None,
            "bluepill_pwm_selftest_stage_enabled": bool(args.with_bluepill_pwm_selftest and not args.skip_hil),
            "bluepill_pwm_selftest_pass": None,
            "hv_stage_enabled": bool(args.with_hv),
            "hv_pass": None,
            "mic_compare_status": "timeout",
            "final_safe": False,
            "overall_pass": False,
        }
        out_path = run_dir / "summary.json"
        write_result_summary(result, out_path)
        log(f"TIMEOUT: {exc.cmd}")
        log(f"SUMMARY: {out_path}")
        return 5


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())
