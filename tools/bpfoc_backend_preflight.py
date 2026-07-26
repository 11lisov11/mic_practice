#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
from urllib import request
from urllib.error import HTTPError

from active_pwm_guard import start_allowed_by_bench_gate
from run_metadata import collect_run_metadata


MODE_DUTY = 2
MODE_BP_FOC = 5
STATUS_LINK_OK = 0x01
STATUS_ENABLED = 0x02
STATUS_PWM_ACTIVE = 0x20


def urlopen_direct(req_or_url, timeout_s: float):
    opener = request.build_opener(request.ProxyHandler({}))
    return opener.open(req_or_url, timeout=timeout_s)


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def http_get_json(url: str, timeout_s: float) -> dict:
    with urlopen_direct(url, timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_cmd(base_url: str, cmd: str, timeout_s: float) -> dict:
    body = json.dumps({"cmd": cmd}).encode("utf-8")
    req = request.Request(
        base_url.rstrip("/") + "/api/cmd",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen_direct(req, timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"ok": False, "error": raw.strip() or f"HTTP {exc.code}"}
        if isinstance(payload, dict):
            payload.setdefault("ok", False)
            payload.setdefault("http_status", exc.code)
            return payload
        return {"ok": False, "error": str(payload), "http_status": exc.code}


def status(base_url: str, timeout_s: float) -> dict:
    payload = http_get_json(base_url.rstrip("/") + "/api/status", timeout_s)
    if not payload.get("ok"):
        raise RuntimeError(f"status failed: {payload}")
    return payload["data"]


def st_int(st: dict, key: str, default: int = 0) -> int:
    try:
        return int(float(st.get(key, default)))
    except Exception:
        return default


def st_float(st: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(st.get(key, default))
    except Exception:
        return default


def observed_vdc(st: dict) -> float:
    values: list[float] = []
    for key in ("bp_vdc", "vdc"):
        if key not in st:
            continue
        value = st_float(st, key, float("nan"))
        if math.isfinite(value) and value >= 0.0:
            values.append(value)
    return max(values) if values else float("nan")


def bp_age_ms(st: dict) -> float:
    ages = []
    for key in ("bp_rsp_age_ms", "bp_age_ms"):
        if key in st:
            ages.append(st_float(st, key, 999999.0))
    return min(ages) if ages else 999999.0


def bp_bad_count(st: dict) -> int:
    values = [st_int(st, key, 999999) for key in ("bp_bad_cnt", "bp_bad") if key in st]
    if not values:
        return 999999
    return max(values)


def status_safe_for_backend_test(
    st: dict,
    max_vdc: float,
    allow_hv: bool,
    require_encoder: bool,
    max_bp_age_ms: float,
) -> tuple[bool, str]:
    if st.get("state") != "SAFE":
        return False, f"state={st.get('state')} expected SAFE"
    if st_int(st, "pwm", 1) != 0:
        return False, "pwm is not 0"
    if st_int(st, "estop", 1) != 0:
        return False, "estop is latched"
    if st_int(st, "bp_fault", 255) != 0:
        return False, f"bp_fault={st.get('bp_fault')}"
    bad = bp_bad_count(st)
    if bad != 0:
        return False, f"bp_bad={bad}"
    if (st_int(st, "bp_status", 0) & STATUS_LINK_OK) == 0:
        return False, f"bp_status=0x{st_int(st, 'bp_status', 0):02x}; Blue Pill link flag is not set"
    age_ms = bp_age_ms(st)
    if age_ms > max_bp_age_ms:
        return False, f"Blue Pill reply age {age_ms:.0f} ms exceeds {max_bp_age_ms:.0f} ms"
    vdc = observed_vdc(st)
    if not math.isfinite(vdc) or vdc < 0.0:
        return False, "Vbus telemetry is not readable"
    if vdc > max_vdc and not allow_hv:
        return False, f"vdc={vdc:.2f} V exceeds max_vdc={max_vdc:.2f}; this is a low-voltage preflight"
    if require_encoder and st_int(st, "enc_ok", 0) != 1:
        return False, "enc_ok is not 1; BP FOC needs measured rotor angle"
    return True, "ok"


def wait_for(base_url: str, timeout_s: float, poll_s: float, pred) -> tuple[bool, dict | None]:
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        last = status(base_url, timeout_s=min(2.0, max(0.2, timeout_s)))
        if pred(last):
            return True, last
        time.sleep(max(0.02, poll_s))
    return False, last


def send_cmd(result: dict, base_url: str, cmd: str, timeout_s: float) -> dict:
    resp = http_post_cmd(base_url, cmd, timeout_s)
    result.setdefault("commands", []).append({"cmd": cmd, "response": resp})
    return resp


def bench_gate_guard(result: dict, base_url: str, label: str) -> dict:
    messages: list[str] = []
    ok = start_allowed_by_bench_gate(messages.append, url=base_url)
    guard = {"label": label, "ok": bool(ok), "messages": messages}
    result.setdefault("bench_gate_guards", []).append(guard)
    return guard


def cmd_ok(resp: dict) -> bool:
    return bool(resp.get("ok"))


def vdc_guard(result: dict, base_url: str, label: str, args) -> dict:
    samples: list[dict] = []
    ok = True
    reason = "ok"
    sample_count = max(1, int(args.vdc_samples))
    for idx in range(sample_count):
        st = status(base_url, args.timeout_s)
        vdc = observed_vdc(st)
        sample = {
            "idx": idx,
            "state": st.get("state"),
            "pwm": st_int(st, "pwm", 1),
            "bp_fault": st_int(st, "bp_fault", 255),
            "bp_bad_cnt": bp_bad_count(st),
            "bp_status": st_int(st, "bp_status", 0),
            "bp_age_ms": bp_age_ms(st),
            "vdc": vdc,
            "bp_vdc": st_float(st, "bp_vdc", float("nan")),
        }
        samples.append(sample)
        safe_ok, safe_reason = status_safe_for_backend_test(
            st,
            max_vdc=float(args.max_vdc),
            allow_hv=bool(args.allow_hv),
            require_encoder=not bool(args.allow_no_encoder),
            max_bp_age_ms=float(args.max_bp_age_ms),
        )
        if not safe_ok:
            ok = False
            reason = safe_reason
        if idx + 1 < sample_count:
            time.sleep(max(0.02, float(args.poll_s)))
    guard = {
        "label": label,
        "ok": ok,
        "reason": reason,
        "max_vdc": max((s["vdc"] for s in samples if math.isfinite(s["vdc"])), default=float("nan")),
        "samples": samples,
    }
    result.setdefault("vdc_guards", []).append(guard)
    return guard


def active_checks(st: dict | None, expected_backend: int, expected_cmd_mode: int, args) -> dict:
    if st is None:
        return {"ok": False, "reason": "missing active status"}
    bp_status = st_int(st, "bp_status", 0)
    checks = {
        "pwm_ok": st_int(st, "pwm", 0) == 1,
        "backend_ok": st_int(st, "bp_foc_backend", -1) == expected_backend,
        "cmd_mode_ok": st_int(st, "bp_cmd_mode", -1) == expected_cmd_mode,
        "bp_mode_ok": True,
        "bp_active_ok": True,
        "bp_status": bp_status,
        "bp_mode": st_int(st, "bp_mode", -1),
        "bp_cmd_mode": st_int(st, "bp_cmd_mode", -1),
    }
    if not bool(args.skip_bp_mode_check):
        checks["bp_mode_ok"] = st_int(st, "bp_mode", -1) == expected_cmd_mode
    if not bool(args.skip_bp_active_check):
        required = STATUS_ENABLED | STATUS_PWM_ACTIVE
        checks["bp_active_ok"] = (bp_status & required) == required
    checks["ok"] = bool(
        checks["pwm_ok"]
        and checks["backend_ok"]
        and checks["cmd_mode_ok"]
        and checks["bp_mode_ok"]
        and checks["bp_active_ok"]
    )
    if not checks["ok"]:
        failed = [k for k in ("pwm_ok", "backend_ok", "cmd_mode_ok", "bp_mode_ok", "bp_active_ok") if not checks[k]]
        checks["reason"] = "failed checks: " + ",".join(failed)
    else:
        checks["reason"] = "ok"
    return checks


def safe_stop(result: dict, base_url: str, timeout_s: float, settle_s: float) -> None:
    for cmd in ("STOP", "SET FREQ 0"):
        try:
            send_cmd(result, base_url, cmd, timeout_s)
        except Exception as exc:
            result.setdefault("cleanup_errors", []).append(f"{cmd}: {exc}")
        time.sleep(min(max(settle_s, 0.05), 0.25))
    try:
        st = status(base_url, timeout_s)
        if st.get("state") == "SAFE" and st_int(st, "pwm", 1) == 0:
            send_cmd(result, base_url, "BPFOC OFF", timeout_s)
    except Exception as exc:
        result.setdefault("cleanup_errors", []).append(f"BPFOC OFF: {exc}")


def run_start_phase(
    result: dict,
    base_url: str,
    label: str,
    expected_backend: int,
    expected_cmd_mode: int,
    args,
) -> tuple[bool, dict]:
    phase: dict = {
        "label": label,
        "expected_backend": expected_backend,
        "expected_cmd_mode": expected_cmd_mode,
        "steps": [],
    }
    result.setdefault("phases", []).append(phase)

    for cmd in ("MODE FOC", f"SET FREQ {float(args.freq):.2f}", f"SET RUNLIMIT {float(args.run_limit_s):.2f}", "START"):
        if cmd == "START":
            guard = vdc_guard(result, base_url, f"{label}_before_start", args)
            phase["vdc_guard"] = guard
            if not guard["ok"]:
                phase["ok"] = False
                phase["error"] = f"pre-start guard failed: {guard['reason']}"
                return False, phase
            bench_guard = bench_gate_guard(result, base_url, f"{label}_before_start")
            phase["bench_gate_guard"] = bench_guard
            if not bench_guard["ok"]:
                phase["ok"] = False
                phase["error"] = "bench gate guard failed before START"
                return False, phase
        resp = send_cmd(result, base_url, cmd, args.timeout_s)
        phase["steps"].append({"cmd": cmd, "ok": cmd_ok(resp), "response": resp})
        if not cmd_ok(resp):
            phase["ok"] = False
            phase["error"] = f"command failed: {cmd}"
            return False, phase
        time.sleep(max(0.02, args.settle_s))

    ok, st = wait_for(
        base_url,
        args.wait_s,
        args.poll_s,
        lambda s: st_int(s, "pwm", 0) == 1
        and active_checks(s, expected_backend, expected_cmd_mode, args)["ok"],
    )
    phase["active_status"] = st
    phase["active_checks"] = active_checks(st, expected_backend, expected_cmd_mode, args)
    phase["active_ok"] = ok
    if not ok:
        phase["ok"] = False
        phase["error"] = "did not observe expected active backend status"
        return False, phase

    time.sleep(max(0.0, args.hold_s))
    safe_stop(result, base_url, args.timeout_s, args.settle_s)
    ok_safe, st_safe = wait_for(
        base_url,
        args.wait_s,
        args.poll_s,
        lambda s: s.get("state") == "SAFE" and st_int(s, "pwm", 1) == 0,
    )
    phase["final_status"] = st_safe
    phase["final_safe"] = ok_safe
    phase["ok"] = bool(ok and ok_safe)
    return bool(phase["ok"]), phase


def main() -> int:
    ap = argparse.ArgumentParser(description="Low-voltage BPFOC backend switch preflight via UNO Q HMI.")
    ap.add_argument("--url", default="http://127.0.0.1:18080", help="HMI base URL")
    ap.add_argument("--freq", type=float, default=1.0, help="Low-voltage FOC command frequency")
    ap.add_argument("--hold-s", type=float, default=0.2, help="Seconds to hold each observed active phase")
    ap.add_argument("--run-limit-s", type=float, default=2.0, help="Firmware run-limit safety for active phases")
    ap.add_argument("--settle-s", type=float, default=0.15)
    ap.add_argument("--poll-s", type=float, default=0.05)
    ap.add_argument("--wait-s", type=float, default=3.0)
    ap.add_argument("--timeout-s", type=float, default=2.0)
    ap.add_argument("--max-vdc", type=float, default=60.0)
    ap.add_argument("--allow-hv", action="store_true", help="Allow running when Vbus is above --max-vdc.")
    ap.add_argument("--allow-no-encoder", action="store_true", help="Do not require enc_ok=1 before BP FOC test.")
    ap.add_argument("--vdc-samples", type=int, default=3, help="Fresh Vbus samples required before every START.")
    ap.add_argument("--max-bp-age-ms", type=float, default=1000.0, help="Maximum accepted Blue Pill reply age.")
    ap.add_argument("--skip-bp-mode-check", action="store_true", help="Do not require Blue Pill last mode to match the commanded mode.")
    ap.add_argument("--skip-bp-active-check", action="store_true", help="Do not require Blue Pill ENABLED/PWM_ACTIVE status bits.")
    ap.add_argument("--out-root", default="tools/_preflight_exports")
    args = ap.parse_args()

    out_dir = Path(args.out_root) / f"bpfoc_backend_preflight_{ts_tag()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "tool": "bpfoc_backend_preflight",
        "url": args.url,
        "run_metadata": collect_run_metadata(Path(__file__).resolve().parents[1]),
        "freq": float(args.freq),
        "max_vdc": float(args.max_vdc),
        "allow_hv": bool(args.allow_hv),
        "require_encoder": not bool(args.allow_no_encoder),
        "vdc_samples": int(args.vdc_samples),
        "max_bp_age_ms": float(args.max_bp_age_ms),
        "require_bp_mode_check": not bool(args.skip_bp_mode_check),
        "require_bp_active_check": not bool(args.skip_bp_active_check),
        "commands": [],
        "phases": [],
        "vdc_guards": [],
    }
    ok = True
    try:
        safe_stop(result, args.url, args.timeout_s, args.settle_s)
        initial = status(args.url, args.timeout_s)
        result["initial_status"] = initial
        pre_ok, pre_reason = status_safe_for_backend_test(
            initial,
            max_vdc=float(args.max_vdc),
            allow_hv=bool(args.allow_hv),
            require_encoder=not bool(args.allow_no_encoder),
            max_bp_age_ms=float(args.max_bp_age_ms),
        )
        result["precondition_ok"] = pre_ok
        result["precondition_reason"] = pre_reason
        if not pre_ok:
            ok = False
        else:
            resp = send_cmd(result, args.url, "BPFOC OFF", args.timeout_s)
            ok = ok and cmd_ok(resp)
            time.sleep(args.settle_s)
            st_off = status(args.url, args.timeout_s)
            result["backend_off_status"] = st_off
            ok = ok and st_int(st_off, "bp_foc_backend", -1) == 0

            duty_ok, duty_phase = run_start_phase(result, args.url, "duty_backend", 0, MODE_DUTY, args)
            ok = ok and duty_ok

            if duty_phase.get("active_status") is not None:
                # Re-enter a short duty-backed active phase to prove the firmware rejects live backend switching.
                block_phase: dict = {"label": "block_live_switch", "expected_reject": True}
                result["phases"].append(block_phase)
                for cmd in ("MODE FOC", f"SET FREQ {float(args.freq):.2f}", f"SET RUNLIMIT {float(args.run_limit_s):.2f}", "START"):
                    if cmd == "START":
                        guard = vdc_guard(result, args.url, "block_live_switch_before_start", args)
                        block_phase["vdc_guard"] = guard
                        if not guard["ok"]:
                            block_phase["ok"] = False
                            block_phase["error"] = f"pre-start guard failed: {guard['reason']}"
                            ok = False
                            break
                        bench_guard = bench_gate_guard(result, args.url, "block_live_switch_before_start")
                        block_phase["bench_gate_guard"] = bench_guard
                        if not bench_guard["ok"]:
                            block_phase["ok"] = False
                            block_phase["error"] = "bench gate guard failed before START"
                            ok = False
                            break
                    resp = send_cmd(result, args.url, cmd, args.timeout_s)
                    block_phase.setdefault("steps", []).append({"cmd": cmd, "ok": cmd_ok(resp), "response": resp})
                    if not cmd_ok(resp):
                        block_phase["ok"] = False
                        block_phase["error"] = f"command failed before block check: {cmd}"
                        ok = False
                        break
                    time.sleep(max(0.02, args.settle_s))
                if "ok" not in block_phase:
                    active_ok, active_st = wait_for(
                        args.url,
                        args.wait_s,
                        args.poll_s,
                        lambda s: active_checks(s, 0, MODE_DUTY, args)["ok"],
                    )
                    block_phase["active_status"] = active_st
                    block_phase["active_checks"] = active_checks(active_st, 0, MODE_DUTY, args)
                    block_phase["active_ok"] = active_ok
                    reject_resp = send_cmd(result, args.url, "BPFOC ON", args.timeout_s)
                    time.sleep(args.settle_s)
                    after_reject = status(args.url, args.timeout_s)
                    block_phase["reject_response"] = reject_resp
                    block_phase["after_reject_status"] = after_reject
                    rejected = not cmd_ok(reject_resp)
                    unchanged = active_checks(after_reject, 0, MODE_DUTY, args)["ok"]
                    block_phase["rejected"] = rejected
                    block_phase["unchanged"] = unchanged
                    block_phase["ok"] = bool(active_ok and rejected and unchanged)
                    ok = ok and bool(block_phase["ok"])
                safe_stop(result, args.url, args.timeout_s, args.settle_s)
                wait_for(args.url, args.wait_s, args.poll_s, lambda s: s.get("state") == "SAFE" and st_int(s, "pwm", 1) == 0)

            resp = send_cmd(result, args.url, "BPFOC ON", args.timeout_s)
            ok = ok and cmd_ok(resp)
            time.sleep(args.settle_s)
            st_on = status(args.url, args.timeout_s)
            result["backend_on_status"] = st_on
            ok = ok and st_int(st_on, "bp_foc_backend", -1) == 1
            bpfoc_ok, _ = run_start_phase(result, args.url, "bpfoc_backend", 1, MODE_BP_FOC, args)
            ok = ok and bpfoc_ok
    except Exception as exc:
        ok = False
        result["error"] = str(exc)
    finally:
        safe_stop(result, args.url, args.timeout_s, args.settle_s)
        try:
            result["final_status"] = status(args.url, args.timeout_s)
        except Exception as exc:
            result["final_status_error"] = str(exc)
            ok = False

    result["pass"] = bool(ok)
    (out_dir / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"pass": bool(ok), "summary": str(out_dir / "summary.json")}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
