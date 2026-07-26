#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime
from pathlib import Path
from urllib import request

from run_metadata import collect_run_metadata


def urlopen_direct(req_or_url, timeout_s: float):
    opener = request.build_opener(request.ProxyHandler({}))
    return opener.open(req_or_url, timeout=timeout_s)


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
    with urlopen_direct(req, timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def status(base_url: str, timeout_s: float) -> dict:
    payload = http_get_json(base_url.rstrip("/") + "/api/status", timeout_s)
    if not payload.get("ok"):
        raise RuntimeError(f"status failed: {payload}")
    return payload["data"]


def st_num(st: dict | None, key: str, default: float = 0.0) -> float:
    if st is None:
        return float(default)
    try:
        val = st.get(key, default)
        if isinstance(val, str):
            val = val.strip()
        num = float(val)
        return num if math.isfinite(num) else float(default)
    except Exception:
        return float(default)


def st_int(st: dict | None, key: str, default: int = 0) -> int:
    return int(st_num(st, key, float(default)))


def bp_link_live(st: dict | None, max_age_ms: float = 1000.0) -> bool:
    if st is None:
        return False
    if st.get("link") is False:
        return False
    ages: list[float] = []
    for key in ("bp_rsp_age_ms", "bp_age_ms"):
        if key in st:
            ages.append(st_num(st, key, 999999.0))
    if st.get("last_rx_age_s") is not None:
        ages.append(st_num(st, "last_rx_age_s", 999999.0) * 1000.0)
    return bool(ages) and min(ages) <= max_age_ms


def bp_bad_count(st: dict | None) -> int:
    if st is None:
        return 999999
    values = [st_int(st, key, 999999) for key in ("bp_bad_cnt", "bp_bad") if key in st]
    if not values:
        return 999999
    return max(values)


def vdc_max_seen(st: dict | None) -> float:
    if st is None:
        return float("nan")
    values: list[float] = []
    for key in ("vdc", "bp_vdc"):
        if key not in st:
            continue
        value = st_num(st, key, float("nan"))
        if math.isfinite(value) and value >= 0.0:
            values.append(value)
    return max(values) if values else float("nan")


def safe_low_voltage(st: dict | None, max_vdc: float, allow_hv: bool) -> tuple[bool, str]:
    if st is None:
        return False, "status unavailable"
    if st.get("state") != "SAFE":
        return False, f"state={st.get('state')}"
    if st_int(st, "pwm", 1) != 0:
        return False, f"pwm={st_int(st, 'pwm', 1)}"
    if st_int(st, "estop", 1) != 0:
        return False, f"estop={st_int(st, 'estop', 1)}"
    if st_int(st, "bp_fault", 255) != 0:
        return False, f"bp_fault={st_int(st, 'bp_fault', 255)}"
    bad = bp_bad_count(st)
    if bad != 0:
        return False, f"bp_bad={bad}"
    if not bp_link_live(st):
        return False, "Blue Pill link stale/down"
    vdc = vdc_max_seen(st)
    if not math.isfinite(vdc) or vdc < 0.0:
        return False, "Vbus telemetry is not readable"
    if not allow_hv and vdc > max_vdc:
        return False, f"Vbus={vdc:.2f} exceeds max_vdc={max_vdc:.2f}"
    return True, "ok"


def fan_cmd_for_duty(duty: float) -> str:
    if duty <= 0.0001:
        return "FAN OFF"
    if duty >= 0.999:
        return "FAN ON"
    return f"FAN PWM {duty:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Low-voltage fan PWM/tach preflight via UNO Q HMI.")
    ap.add_argument("--url", default="http://127.0.0.1:18080", help="HMI base URL")
    ap.add_argument("--duties", default="0,0.3,0.6,1.0,0", help="comma-separated fan duty sequence")
    ap.add_argument("--settle-s", type=float, default=0.8)
    ap.add_argument("--timeout-s", type=float, default=2.0)
    ap.add_argument("--tolerance", type=float, default=0.10, help="accepted duty mismatch")
    ap.add_argument("--require-tach", action="store_true", help="require non-zero tach rpm at duties >= 0.3")
    ap.add_argument("--allow-running", action="store_true", help="do not require SAFE/pwm=0 before testing")
    ap.add_argument("--max-vdc", type=float, default=60.0, help="Low-voltage precondition threshold.")
    ap.add_argument("--allow-hv", action="store_true", help="Allow fan preflight when Vbus is above --max-vdc.")
    ap.add_argument("--out-root", default="tools/_preflight_exports")
    args = ap.parse_args()

    duties = []
    for token in args.duties.split(","):
        token = token.strip()
        if not token:
            continue
        duty = max(0.0, min(1.0, float(token)))
        duties.append(duty)
    if not duties:
        raise SystemExit("no duties specified")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    out_dir = Path(args.out_root) / f"fan_preflight_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "tool": "fan_preflight",
        "url": args.url,
        "run_metadata": collect_run_metadata(Path(__file__).resolve().parents[1]),
        "duties": duties,
        "settle_s": args.settle_s,
        "require_tach": args.require_tach,
        "max_vdc": args.max_vdc,
        "allow_hv": bool(args.allow_hv),
        "steps": [],
    }

    ok = True
    try:
        initial = status(args.url, args.timeout_s)
        result["initial_status"] = initial
        if not args.allow_running:
            safe, reason = safe_low_voltage(initial, args.max_vdc, bool(args.allow_hv))
            result["pre_safe_low_voltage"] = {"ok": safe, "reason": reason}
            if not safe:
                ok = False
                result["precondition_error"] = f"bench is not safe low-voltage: {reason}"

        if ok:
            for duty in duties:
                cmd = fan_cmd_for_duty(duty)
                cmd_resp = http_post_cmd(args.url, cmd, args.timeout_s)
                time.sleep(args.settle_s)
                st = status(args.url, args.timeout_s)
                fan_duty = float(st.get("fan_duty", 0.0))
                bp_fan_duty = float(st.get("bp_fan_duty", 0.0))
                bp_fan_rpm = float(st.get("bp_fan_rpm", 0.0))
                duty_ok = abs(fan_duty - duty) <= args.tolerance
                bp_duty_ok = abs(bp_fan_duty - duty) <= args.tolerance
                tach_ok = True
                if args.require_tach and duty >= 0.3:
                    tach_ok = bp_fan_rpm > 0.0
                step_ok = bool(cmd_resp.get("ok")) and duty_ok and bp_duty_ok and tach_ok
                ok = ok and step_ok
                result["steps"].append(
                    {
                        "cmd": cmd,
                        "target_duty": duty,
                        "cmd_ok": bool(cmd_resp.get("ok")),
                        "fan_duty": fan_duty,
                        "bp_fan_duty": bp_fan_duty,
                        "bp_fan_rpm": bp_fan_rpm,
                        "duty_ok": duty_ok,
                        "bp_duty_ok": bp_duty_ok,
                        "tach_ok": tach_ok,
                        "ok": step_ok,
                    }
                )
    finally:
        try:
            http_post_cmd(args.url, "FAN OFF", args.timeout_s)
            time.sleep(min(args.settle_s, 0.5))
            final = status(args.url, args.timeout_s)
            result["final_status"] = final
            if not args.allow_running:
                final_safe, final_reason = safe_low_voltage(final, args.max_vdc, bool(args.allow_hv))
                result["final_safe_low_voltage"] = {"ok": final_safe, "reason": final_reason}
                ok = ok and final_safe
        except Exception as exc:
            result["cleanup_error"] = str(exc)
            ok = False

    result["pass"] = ok
    (out_dir / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"pass": ok, "summary": str(out_dir / "summary.json")}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
