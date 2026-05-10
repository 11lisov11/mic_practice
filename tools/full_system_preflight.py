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


def log(msg: str) -> None:
    print(msg, flush=True)


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


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
    return (
        int(status_num(st, "pwm", 1.0)) == 0
        and int(status_num(st, "estop", 1.0)) == 0
        and st.get("state") == "SAFE"
        and bp_link_live(st)
        and int(status_num(st, "bp_fault", 255.0)) == 0
        and int(status_num(st, "bp_bad", 999999.0)) == 0
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
    ap.add_argument("--skip-hil", action="store_true")
    ap.add_argument("--skip-full-suite", action="store_true")
    ap.add_argument("--skip-mic-compare", action="store_true")
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
    hv_dir = run_dir / "hv_j7"
    logs_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "ts": run_dir.name.rsplit("_", 1)[-1],
        "base_url": args.url.rstrip("/"),
        "run_dir": str(run_dir),
        "steps": [],
    }

    def step(name: str, cmd: list[str], workdir: Path, timeout_s: float) -> dict:
        info = run_step(name, cmd, str(workdir), logs_dir / f"{name}.log", timeout_s)
        result["steps"].append(info)
        return info

    try:
        if not args.skip_build:
            step(
                "py_compile",
                [
                    sys.executable,
                    "-m",
                    "py_compile",
                    "tools\\adb_deploy_web_hmi.py",
                    "tools\\encoder_test.py",
                    "tools\\logic2_recover.py",
                    "tools\\ui_access.py",
                    "tools\\ui_pwm_case.py",
                    "tools\\ui_pwm_suite.py",
                    "tools\\scalar_vf_preflight.py",
                    "tools\\foc_mic_preflight.py",
                    "tools\\hv_j7_preflight.py",
                    "tools\\mic_ai_compare.py",
                    "tools\\full_system_preflight.py",
                    "tools\\unoq_web_server.py",
                    "web_hmi\\server.py",
                ],
                repo_root,
                args.timeout_build,
            )
            step(
                "unoq_build",
                ["arduino-cli", "compile", "--fqbn", "arduino:zephyr:unoq", ".\\UNOQ_MOTOR"],
                repo_root,
                args.timeout_build,
            )
            step(
                "bluepill_build",
                [sys.executable, "-m", "platformio", "run"],
                repo_root / "bluepill_uart_pwm_pio",
                args.timeout_build,
            )

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
                            "1.0",
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

        build_steps = [s for s in result["steps"] if s["name"] in ("py_compile", "unoq_build", "bluepill_build")]
        required_hil = [
            s
            for s in result["steps"]
            if s["name"] in ("ui_access", "encoder_test", "scalar_vf_preflight", "foc_mic_preflight")
        ]
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

        result["summary"] = {
            "build_pass": all(s["ok"] for s in build_steps) if build_steps else True,
            "required_hil_pass": (all(s["ok"] for s in required_hil) if required_hil else True) and logic_ok,
            "full_suite_pass": full_suite_pass,
            "hv_stage_enabled": bool(args.with_hv),
            "hv_pass": (result["hv_summary"] or {}).get("pass") if args.with_hv else None,
            "mic_compare_status": result["mic_compare_classification"]["status"] if not args.skip_mic_compare else "skipped",
            "final_safe": status_is_safe(status_after),
        }
        result["summary"]["overall_pass"] = bool(
            result["summary"]["build_pass"]
            and result["summary"]["required_hil_pass"]
            and result["summary"]["full_suite_pass"]
            and result["summary"]["final_safe"]
        )

        out_path = run_dir / "summary.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"SUMMARY: {out_path}")
        log(f"PASS={result['summary']['overall_pass']}")
        return 0 if result["summary"]["overall_pass"] else 4
    except subprocess.TimeoutExpired as exc:
        result["timeout"] = {
            "cmd": exc.cmd,
            "timeout_s": exc.timeout,
        }
        out_path = run_dir / "summary.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"TIMEOUT: {exc.cmd}")
        log(f"SUMMARY: {out_path}")
        return 5


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())
