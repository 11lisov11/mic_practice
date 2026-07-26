#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
import urllib.error
import urllib.request

from active_pwm_guard import start_allowed_by_bench_gate
from run_metadata import collect_run_metadata  # noqa: E402


BP_MAX_AGE_MS = 1000.0
START_ALLOW_HV = False
START_MAX_VDC = 60.0
START_VDC_SAMPLES = 3
DEFAULT_RUN_LIMIT_S = float(os.environ.get("UNOQ_TEST_RUNLIMIT_S", "3.0"))


def log(msg: str) -> None:
    print(msg, flush=True)


def truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def http_json(url: str, body: dict | None = None, timeout: float = 6.5) -> dict | None:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_exc = exc
            transient = exc.code in (500, 502, 503, 504)
        except Exception as exc:
            last_exc = exc
            transient = True
        if transient and attempt < 2:
            time.sleep(0.15 * (attempt + 1))
            continue
        break
    log(f"HTTP error: {last_exc}")
    return None


def get_status(base: str) -> dict | None:
    resp = http_json(base.rstrip("/") + "/api/status")
    if not resp or not resp.get("ok"):
        return None
    return resp.get("data")


def st_num(st: dict, key: str, default: float = 0.0) -> float:
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


def bp_link_live(st: dict | None, max_age_ms: float = BP_MAX_AGE_MS) -> bool:
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


def bp_cmd_bad_ok(st: dict | None) -> bool:
    if st is None:
        return False
    values = [int(st_num(st, key, 999999.0)) for key in ("bp_bad_cnt", "bp_bad") if key in st]
    if not values:
        return False
    return max(values) == 0


def status_is_safe(st: dict | None, allow_estop: bool = False) -> bool:
    if st is None:
        return False
    estop = int(st_num(st, "estop", 1.0))
    bp_fault_free = int(st_num(st, "bp_fault", 255.0)) == 0
    return (
        st.get("state") == "SAFE"
        and int(st_num(st, "pwm", 1.0)) == 0
        and bp_link_live(st)
        and bp_cmd_bad_ok(st)
        and (allow_estop or estop == 0)
        and (allow_estop or bp_fault_free)
    )


def status_mode_matches(st: dict | None, expected_mode: str) -> bool:
    if st is None:
        return False
    mode_name = str(st.get("mode", ""))
    diag_mode = int(st_num(st, "diag_mode", -1.0))
    duty_mode = int(st_num(st, "duty_mode", -1.0))
    if expected_mode == "VF":
        if diag_mode >= 0 and duty_mode >= 0:
            return mode_name == "VF" and diag_mode == 0 and duty_mode == 0
        return mode_name == "VF"
    return mode_name == expected_mode


def wait_for(base: str, predicate, timeout_s: float, poll_s: float) -> tuple[bool, dict | None, float]:
    start = time.monotonic()
    last = None
    while (time.monotonic() - start) < timeout_s:
        st = get_status(base)
        if st is not None:
            last = st
            if predicate(st):
                return True, st, (time.monotonic() - start)
        time.sleep(poll_s)
    return False, last, (time.monotonic() - start)


def wait_http_ready(base: str, timeout_s: float, poll_s: float) -> tuple[bool, dict | None, float]:
    return wait_for(base, lambda _st: True, timeout_s=timeout_s, poll_s=poll_s)


def status_vdc(st: dict | None) -> float:
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


def max_start_vdc() -> float:
    return float(START_MAX_VDC)


def start_vdc_samples() -> int:
    return max(1, int(START_VDC_SAMPLES))


def command_requests_start(cmd: str) -> bool:
    return cmd.strip().upper() == "START"


def command_sets_runlimit(cmd: str) -> bool:
    return cmd.strip().upper().startswith("SET RUNLIMIT")


def command_clears_runlimit(cmd: str) -> bool:
    upper = cmd.strip().upper()
    return upper in ("CLEAR", "RESET", "STOP", "ESTOP", "ESTOP CLEAR")


def commands_with_runlimit(cmds: list[str], default_s: float | None = None) -> list[str]:
    run_limit_s = DEFAULT_RUN_LIMIT_S if default_s is None else float(default_s)
    run_limit_s = max(0.1, min(600.0, run_limit_s))
    out: list[str] = []
    runlimit_ready = False
    for cmd in cmds:
        if command_clears_runlimit(cmd):
            runlimit_ready = False
        if command_sets_runlimit(cmd):
            runlimit_ready = True
        if command_requests_start(cmd) and not runlimit_ready:
            out.append(f"SET RUNLIMIT {run_limit_s:.3f}")
            runlimit_ready = True
        out.append(cmd)
        if command_requests_start(cmd):
            runlimit_ready = False
    return out


def start_allowed_by_vdc(base: str) -> bool:
    limit = max_start_vdc()
    samples: list[float] = []
    for idx in range(start_vdc_samples()):
        vdc = status_vdc(get_status(base))
        if math.isfinite(vdc) and vdc >= 0.0:
            samples.append(vdc)
        if idx + 1 < start_vdc_samples():
            time.sleep(0.05)
    if not samples:
        log("ERROR: START blocked: status/vdc is not readable. Fix Vbus telemetry before any START.")
        return False
    vdc = max(samples)
    if vdc > limit and not START_ALLOW_HV:
        log(
            f"ERROR: START blocked: max sampled vdc={vdc:.2f} V exceeds --max-start-vdc={limit:.2f} V. "
            "Remove/discharge HV or pass --allow-hv for an intentional HV run."
        )
        return False
    return True


def post_cmd(base: str, cmd: str) -> bool:
    if command_requests_start(cmd):
        if not start_allowed_by_vdc(base):
            return False
        if not start_allowed_by_bench_gate(log, url=base):
            return False
    resp = http_json(base.rstrip("/") + "/api/cmd", {"cmd": cmd})
    return bool(resp and resp.get("ok"))


def send_cmds(base: str, cmds: list[str]) -> bool:
    ok = True
    for cmd in cmds:
        if not post_cmd(base, cmd):
            log(f"ERROR: UI cmd failed: {cmd}")
            ok = False
    return ok


def send_cmds_retry(base: str, cmds: list[str], retries: int = 1, retry_delay_s: float = 0.15) -> bool:
    guarded_cmds = commands_with_runlimit(cmds)
    for attempt in range(retries + 1):
        ok = send_cmds(base, guarded_cmds)
        if ok:
            return True
        if attempt < retries:
            log(f"WARN: cmd send failed, retry {attempt + 1}/{retries}")
            time.sleep(retry_delay_s)
    return False


def safe_stop(base: str) -> None:
    try:
        wait_http_ready(base, timeout_s=2.0, poll_s=0.1)
        send_cmds_retry(base, ["STOP"], retries=2, retry_delay_s=0.2)
        ok, st, dt = wait_for(base, lambda s: status_is_safe(s, allow_estop=True), timeout_s=1.5, poll_s=0.05)
        if not ok:
            log(f"WARN: STOP not confirmed after {dt*1000:.1f}ms st={st}")
            wait_http_ready(base, timeout_s=2.0, poll_s=0.1)
            send_cmds_retry(base, ["ESTOP"], retries=2, retry_delay_s=0.2)
            estop_ok, estop_st, estop_dt = wait_for(
                base,
                lambda s: status_is_safe(s, allow_estop=True),
                timeout_s=1.5,
                poll_s=0.05,
            )
            if not estop_ok:
                log(f"WARN: ESTOP cleanup not confirmed after {estop_dt*1000:.1f}ms st={estop_st}")
        wait_http_ready(base, timeout_s=2.0, poll_s=0.1)
        send_cmds_retry(base, ["CLEAR"], retries=2, retry_delay_s=0.2)
        clear_ok, clear_st, clear_dt = wait_for(
            base,
            lambda s: status_is_safe(s, allow_estop=False),
            timeout_s=2.0,
            poll_s=0.05,
        )
        if not clear_ok:
            log(f"WARN: CLEAR not confirmed after {clear_dt*1000:.1f}ms st={clear_st}")
    except Exception as exc:
        log(f"WARN: safe_stop failed: {exc}")


@dataclass
class Sample:
    t_s: float
    st: dict


def _ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _mean(xs: list[float]) -> float | None:
    if not xs:
        return None
    return float(sum(xs) / len(xs))


def _as_float(v) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _compute_enc_rpm(samples: list[Sample]) -> list[float | None]:
    # Use firmware-provided enc_rpm if present, else estimate from enc_raw deltas.
    fw_vals: list[float | None] = []
    for s in samples:
        fw_vals.append(_as_float(s.st.get("enc_rpm", None)))
    fw_non_none = [v for v in fw_vals if v is not None]
    fw_has_motion = any(abs(v) > 0.5 for v in fw_non_none)
    # If firmware exposes a non-trivial speed signal, trust it.
    # If it is all zeros, derive from enc_raw to avoid false "0 rpm" summaries.
    if fw_non_none and fw_has_motion:
        return fw_vals

    out = [None for _ in samples]
    prev_raw = None
    prev_t = None
    for i, s in enumerate(samples):
        if int(st_num(s.st, "enc_ok", 0.0)) != 1:
            prev_raw = None
            prev_t = None
            continue
        raw = int(st_num(s.st, "enc_raw", -1.0))
        if raw < 0:
            continue
        if prev_raw is None:
            prev_raw = raw
            prev_t = s.t_s
            continue
        dt = s.t_s - (prev_t if prev_t is not None else s.t_s)
        if dt <= 1e-6:
            continue
        dr = raw - prev_raw
        if dr > 2048:
            dr -= 4096
        elif dr < -2048:
            dr += 4096
        rpm = (dr / 4096.0) / dt * 60.0
        out[i] = float(rpm)
        prev_raw = raw
        prev_t = s.t_s
    return out


def _write_timeseries_csv(path: str, samples: list[Sample], extra_cols: dict[str, list[float | None]]) -> None:
    keys = [
        "ts",
        "state",
        "mode",
        "pwm",
        "freq_cmd",
        "freq",
        "speed",
        "vdc",
        "i_rms",
        "id",
        "iq",
        "mic_active",
        "id_ref",
        "mic_saving_pct",
        "enc_ok",
        "enc_raw",
        "enc_deg",
        "mic_gated",
        "mic_enable_ai",
        "mic_enc_used",
        "mic_freq_meas_hz",
        "mic_speed_err_hz",
        "mic_speed_tol_hz",
        "mic_link_flags",
        "mic_status_flags",
        "bp_mode",
        "bp_cmd_mode",
        "bp_foc_backend",
    ]
    cols = ["t_s"] + keys + list(extra_cols.keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, s in enumerate(samples):
            st = s.st
            row = [f"{s.t_s:.6f}"]
            for k in keys:
                row.append(st.get(k, ""))
            for k in extra_cols.keys():
                v = extra_cols[k][i]
                row.append("" if v is None else f"{float(v):.6f}")
            w.writerow(row)


def _summarize(samples: list[Sample], enc_rpm: list[float | None]) -> dict:
    pwm_ones = sum(1 for s in samples if int(st_num(s.st, "pwm", 0.0)) == 1)
    enc_ok = sum(1 for s in samples if int(st_num(s.st, "enc_ok", 0.0)) == 1)
    mic_on = sum(1 for s in samples if int(st_num(s.st, "mic_active", 0.0)) == 1)
    mic_enable_ai = sum(1 for s in samples if int(st_num(s.st, "mic_enable_ai", 0.0)) == 1)
    mic_gated = sum(1 for s in samples if int(st_num(s.st, "mic_gated", 0.0)) != 0)

    def f(key: str) -> list[float]:
        out: list[float] = []
        for s in samples:
            v = _as_float(s.st.get(key, None))
            if v is None:
                continue
            out.append(float(v))
        return out

    p_proxy: list[float] = []
    for s in samples:
        vdc = _as_float(s.st.get("vdc", None))
        i_rms = _as_float(s.st.get("i_rms", None))
        if vdc is None or i_rms is None:
            continue
        p_proxy.append(float(vdc * i_rms))

    out = {
        "samples": len(samples),
        "pwm_ratio": (pwm_ones / len(samples)) if samples else 0.0,
        "enc_ok_ratio": (enc_ok / len(samples)) if samples else 0.0,
        "mic_active_ratio": (mic_on / len(samples)) if samples else 0.0,
        "mic_enable_ai_ratio": (mic_enable_ai / len(samples)) if samples else 0.0,
        "mic_gated_ratio": (mic_gated / len(samples)) if samples else 0.0,
        "mean_i_rms": _mean(f("i_rms")),
        "mean_vdc": _mean(f("vdc")),
        "mean_speed_cmd_rpm": _mean(f("speed")),
        "mean_freq_cmd_hz": _mean(f("freq_cmd")),
        "mean_freq_ref_hz": _mean(f("freq")),
        "mean_id": _mean(f("id")),
        "mean_iq": _mean(f("iq")),
        "mean_id_ref": _mean(f("id_ref")),
        "mean_mic_saving_pct": _mean(f("mic_saving_pct")),
        "mean_mic_freq_meas_hz": _mean(f("mic_freq_meas_hz")),
        "mean_mic_speed_err_hz": _mean(f("mic_speed_err_hz")),
        "mean_mic_speed_tol_hz": _mean(f("mic_speed_tol_hz")),
        "mean_enc_rpm": _mean([x for x in enc_rpm if x is not None]),
        "mean_p_proxy": _mean(p_proxy),
        "states": sorted({str(s.st.get("state", "")) for s in samples}),
        "modes": sorted({str(s.st.get("mode", "")) for s in samples}),
        "mic_link_flags_values": sorted({int(st_num(s.st, "mic_link_flags", 0.0)) for s in samples}),
        "mic_status_flags_values": sorted({int(st_num(s.st, "mic_status_flags", 0.0)) for s in samples}),
        "mic_enc_used_values": sorted({int(st_num(s.st, "mic_enc_used", 0.0)) for s in samples}),
        "bp_mode_values": sorted({int(st_num(s.st, "bp_mode", 0.0)) for s in samples}),
        "bp_cmd_mode_values": sorted({int(st_num(s.st, "bp_cmd_mode", st_num(s.st, "bp_mode", 0.0))) for s in samples}),
        "bp_foc_backend_values": sorted({int(st_num(s.st, "bp_foc_backend", 0.0)) for s in samples}),
    }
    if out["mean_speed_cmd_rpm"] is not None and out["mean_enc_rpm"] is not None:
        out["mean_speed_err_rpm"] = float(out["mean_speed_cmd_rpm"] - out["mean_enc_rpm"])
    else:
        out["mean_speed_err_rpm"] = None
    return out


def _run_mode(
    base: str,
    mode: str,
    freq: float,
    duration_s: float,
    poll_s: float,
    warmup_s: float,
    status_timeout_s: float,
    cmd_retries: int,
    cmd_retry_delay_s: float,
) -> tuple[bool, dict | None, list[Sample]]:
    cmds = ["CLEAR", f"MODE {mode}", f"SET FREQ {freq:.1f}", "START"]
    ui_ok, ui_st, ui_dt = wait_http_ready(base, timeout_s=max(2.0, status_timeout_s), poll_s=max(0.05, poll_s))
    log(f"UI ready before {mode}: ok={ui_ok} dt={ui_dt*1000:.1f}ms st={ui_st}")
    if not ui_ok:
        return False, ui_st, []
    if not send_cmds_retry(base, cmds, retries=cmd_retries, retry_delay_s=cmd_retry_delay_s):
        return False, None, []

    def pred(st: dict) -> bool:
        if not status_mode_matches(st, mode):
            return False
        if int(st_num(st, "pwm", 0.0)) != 1:
            return False
        if abs(st_num(st, "freq_cmd", 0.0) - float(freq)) > 0.06:
            return False
        if mode in ("FOC", "MIC") and st.get("state") not in ("FOC_ALIGN", "FOC_RUN"):
            return False
        if mode == "VF" and st.get("state") != "VF_RUN":
            return False
        return True

    ok, st, dt = wait_for(base, pred, timeout_s=status_timeout_s, poll_s=max(0.02, poll_s))
    log(f"Status mode={mode} ok={ok} dt={dt*1000:.1f}ms st={st}")
    if not ok:
        return False, st, []

    if warmup_s > 0:
        time.sleep(warmup_s)

    samples: list[Sample] = []
    start = time.monotonic()
    while (time.monotonic() - start) < duration_s:
        st = get_status(base)
        if st is not None:
            samples.append(Sample(t_s=(time.monotonic() - start), st=st))
        time.sleep(poll_s)
    return True, st, samples


def _run_mode_with_retry(
    base: str,
    mode: str,
    freq: float,
    duration_s: float,
    poll_s: float,
    warmup_s: float,
    status_timeout_s: float,
    mode_retries: int,
    cmd_retries: int,
    cmd_retry_delay_s: float,
    settle_s: float,
) -> tuple[bool, dict | None, list[Sample]]:
    last_st = None
    last_samples: list[Sample] = []
    for attempt in range(mode_retries + 1):
        if attempt:
            log(f"WARN: retry {mode} compare phase attempt {attempt + 1}/{mode_retries + 1}")
            safe_stop(base)
            time.sleep(settle_s)
        ok, st, samples = _run_mode(
            base=base,
            mode=mode,
            freq=freq,
            duration_s=duration_s,
            poll_s=poll_s,
            warmup_s=warmup_s,
            status_timeout_s=status_timeout_s,
            cmd_retries=cmd_retries,
            cmd_retry_delay_s=cmd_retry_delay_s,
        )
        safe_stop(base)
        last_st = st
        last_samples = samples
        if ok and samples:
            return True, st, samples
        time.sleep(settle_s)
    return False, last_st, last_samples


def main() -> int:
    ap = argparse.ArgumentParser(description="FOC vs MIC timeseries compare via UNOQ /api/status (finite).")
    ap.add_argument("--url", default="http://127.0.0.1:18080")
    ap.add_argument("--freq", type=float, default=10.0)
    ap.add_argument("--duration", type=float, default=8.0, help="Seconds per mode (finite)")
    ap.add_argument("--poll", type=float, default=0.05)
    ap.add_argument("--warmup", type=float, default=0.8, help="Seconds to wait after START before sampling")
    ap.add_argument("--status-timeout", type=float, default=1.2)
    ap.add_argument("--outdir", default=os.path.join(os.path.dirname(__file__), "_mic_ai_exports"))
    ap.add_argument("--tag", default="")
    ap.add_argument("--min-mic-active-ratio", type=float, default=0.05)
    ap.add_argument("--max-i-rms-increase-pct", type=float, default=2.0)
    ap.add_argument("--max-p-proxy-increase-pct", type=float, default=3.0)
    ap.add_argument("--max-enc-rpm-delta-pct", type=float, default=8.0)
    ap.add_argument("--min-enc-rpm-for-speed-check", type=float, default=50.0)
    ap.add_argument("--min-mic-saving-pct", type=float, default=0.0)
    ap.add_argument("--require-encoder", action="store_true")
    ap.add_argument("--allow-hv", action="store_true", help="Allow START when measured Vbus is above --max-start-vdc.")
    ap.add_argument("--max-start-vdc", type=float, default=None, help="Low-voltage START guard threshold; default 60 V or UNOQ_MAX_START_VDC.")
    ap.add_argument("--start-vdc-samples", type=int, default=None, help="Vbus samples before each START; default 3 or UNOQ_START_VDC_SAMPLES.")
    ap.add_argument("--mode-retries", type=int, default=1)
    ap.add_argument("--cmd-retries", type=int, default=2)
    ap.add_argument("--cmd-retry-delay", type=float, default=0.2)
    ap.add_argument("--settle", type=float, default=0.4, help="Seconds to settle between compare phases/retries")
    args = ap.parse_args()

    global START_ALLOW_HV, START_MAX_VDC, START_VDC_SAMPLES
    START_ALLOW_HV = bool(args.allow_hv) or truthy_env("UNOQ_ALLOW_HV")
    if args.max_start_vdc is not None:
        START_MAX_VDC = float(args.max_start_vdc)
    else:
        try:
            START_MAX_VDC = float(os.environ.get("UNOQ_MAX_START_VDC", "60.0"))
        except Exception:
            START_MAX_VDC = 60.0
    if args.start_vdc_samples is not None:
        START_VDC_SAMPLES = max(1, int(args.start_vdc_samples))
    else:
        try:
            START_VDC_SAMPLES = max(1, int(os.environ.get("UNOQ_START_VDC_SAMPLES", "3")))
        except Exception:
            START_VDC_SAMPLES = 3

    base = args.url.rstrip("/")
    freq = float(args.freq)
    duration_s = max(0.2, float(args.duration))
    poll_s = max(0.01, float(args.poll))
    warmup_s = max(0.0, float(args.warmup))
    status_timeout_s = max(0.2, float(args.status_timeout))

    tag = args.tag.strip() or f"mic_compare_{freq:.1f}Hz".replace(".", "p")
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)
    run_dir = os.path.join(outdir, f"{tag}_{_ts_tag()}")
    os.makedirs(run_dir, exist_ok=True)

    log(f"START mic_ai_compare tag={tag} freq={freq:.1f} url={base}")
    log(f"OUT {run_dir}")

    try:
        ok_foc, st_foc, samples_foc = _run_mode(
            base=base,
            mode="FOC",
            freq=freq,
            duration_s=duration_s,
            poll_s=poll_s,
            warmup_s=warmup_s,
            status_timeout_s=status_timeout_s,
            cmd_retries=int(args.cmd_retries),
            cmd_retry_delay_s=float(args.cmd_retry_delay),
        )
        safe_stop(base)
        if not ok_foc or not samples_foc:
            ok_foc, st_foc, samples_foc = _run_mode_with_retry(
                base=base,
                mode="FOC",
                freq=freq,
                duration_s=duration_s,
                poll_s=poll_s,
                warmup_s=warmup_s,
                status_timeout_s=status_timeout_s,
                mode_retries=max(0, int(args.mode_retries)),
                cmd_retries=int(args.cmd_retries),
                cmd_retry_delay_s=float(args.cmd_retry_delay),
                settle_s=max(0.0, float(args.settle)),
            )
        if not ok_foc or not samples_foc:
            log("FAIL: FOC sampling failed")
            return 2

        ok_mic, st_mic, samples_mic = _run_mode_with_retry(
            base=base,
            mode="MIC",
            freq=freq,
            duration_s=duration_s,
            poll_s=poll_s,
            warmup_s=warmup_s,
            status_timeout_s=status_timeout_s,
            mode_retries=max(0, int(args.mode_retries)),
            cmd_retries=int(args.cmd_retries),
            cmd_retry_delay_s=float(args.cmd_retry_delay),
            settle_s=max(0.0, float(args.settle)),
        )
        if not ok_mic or not samples_mic:
            log("FAIL: MIC sampling failed")
            return 3

        enc_rpm_foc = _compute_enc_rpm(samples_foc)
        enc_rpm_mic = _compute_enc_rpm(samples_mic)

        foc_csv = os.path.join(run_dir, "timeseries_foc.csv")
        mic_csv = os.path.join(run_dir, "timeseries_mic.csv")
        _write_timeseries_csv(foc_csv, samples_foc, {"enc_rpm_est": enc_rpm_foc})
        _write_timeseries_csv(mic_csv, samples_mic, {"enc_rpm_est": enc_rpm_mic})

        foc_sum = _summarize(samples_foc, enc_rpm_foc)
        mic_sum = _summarize(samples_mic, enc_rpm_mic)

        def pct_delta(a: float | None, b: float | None) -> float | None:
            if a is None or b is None:
                return None
            if abs(a) < 1e-9:
                return None
            return float((b - a) / a * 100.0)

        diff = {
            "i_rms_pct": pct_delta(foc_sum.get("mean_i_rms"), mic_sum.get("mean_i_rms")),
            "id_ref_pct": pct_delta(foc_sum.get("mean_id_ref"), mic_sum.get("mean_id_ref")),
            "mic_saving_pct_mean": mic_sum.get("mean_mic_saving_pct"),
            "enc_rpm_pct": pct_delta(foc_sum.get("mean_enc_rpm"), mic_sum.get("mean_enc_rpm")),
            "p_proxy_pct": pct_delta(foc_sum.get("mean_p_proxy"), mic_sum.get("mean_p_proxy")),
        }

        mic_active_ratio = float(mic_sum.get("mic_active_ratio") or 0.0)
        i_rms_pct = diff.get("i_rms_pct")
        p_proxy_pct = diff.get("p_proxy_pct")
        enc_rpm_pct = diff.get("enc_rpm_pct")
        mic_saving_mean = mic_sum.get("mean_mic_saving_pct")
        foc_mean_enc_rpm = foc_sum.get("mean_enc_rpm")
        foc_enc_ok_ratio = float(foc_sum.get("enc_ok_ratio") or 0.0)
        mic_enc_ok_ratio = float(mic_sum.get("enc_ok_ratio") or 0.0)

        checks: dict[str, bool] = {}
        checks["mic_active_ratio"] = mic_active_ratio >= float(args.min_mic_active_ratio)
        checks["i_rms_not_worse"] = (i_rms_pct is not None) and (float(i_rms_pct) <= float(args.max_i_rms_increase_pct))
        checks["p_proxy_not_worse"] = (p_proxy_pct is not None) and (
            float(p_proxy_pct) <= float(args.max_p_proxy_increase_pct)
        )
        checks["mic_saving_estimate"] = (mic_saving_mean is not None) and (
            float(mic_saving_mean) >= float(args.min_mic_saving_pct)
        )

        use_enc_speed_check = (foc_mean_enc_rpm is not None) and (
            abs(float(foc_mean_enc_rpm)) >= float(args.min_enc_rpm_for_speed_check)
        )
        speed_ok = True
        if use_enc_speed_check and enc_rpm_pct is not None:
            speed_ok = abs(float(enc_rpm_pct)) <= float(args.max_enc_rpm_delta_pct)
        elif use_enc_speed_check and bool(args.require_encoder):
            speed_ok = False
        checks["speed_preserved"] = speed_ok

        if bool(args.require_encoder):
            checks["encoder_present"] = (foc_enc_ok_ratio >= 0.7) and (mic_enc_ok_ratio >= 0.7)
        else:
            checks["encoder_present"] = True

        passed = all(checks.values())

        summary = {
            "tag": tag,
            "run_metadata": collect_run_metadata(os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))),
            "freq_cmd_hz": freq,
            "duration_s": duration_s,
            "poll_s": poll_s,
            "warmup_s": warmup_s,
            "thresholds": {
                "min_mic_active_ratio": float(args.min_mic_active_ratio),
                "max_i_rms_increase_pct": float(args.max_i_rms_increase_pct),
                "max_p_proxy_increase_pct": float(args.max_p_proxy_increase_pct),
                "max_enc_rpm_delta_pct": float(args.max_enc_rpm_delta_pct),
                "min_enc_rpm_for_speed_check": float(args.min_enc_rpm_for_speed_check),
                "min_mic_saving_pct": float(args.min_mic_saving_pct),
                "require_encoder": bool(args.require_encoder),
                "allow_hv": bool(START_ALLOW_HV),
                "max_start_vdc": float(START_MAX_VDC),
                "start_vdc_samples": int(START_VDC_SAMPLES),
            },
            "foc": foc_sum,
            "mic": mic_sum,
            "diff": diff,
            "checks": checks,
            "pass": passed,
            "files": {"foc_csv": foc_csv, "mic_csv": mic_csv},
        }
        summary_path = os.path.join(run_dir, "summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        log(
            f"FOC mean_i_rms={foc_sum.get('mean_i_rms')} MIC mean_i_rms={mic_sum.get('mean_i_rms')} i_rms_pct={diff.get('i_rms_pct')}"
        )
        log(
            f"FOC mean_p_proxy={foc_sum.get('mean_p_proxy')} MIC mean_p_proxy={mic_sum.get('mean_p_proxy')} p_proxy_pct={diff.get('p_proxy_pct')}"
        )
        log(
            f"MIC mic_active_ratio={mic_active_ratio:.3f} mic_saving_pct_mean={mic_sum.get('mean_mic_saving_pct')} enc_rpm_pct={diff.get('enc_rpm_pct')}"
        )
        log(f"Checks: {checks}")
        log(f"Summary: {summary_path}")
        log(f"PASS={passed}")
        return 0 if passed else 4
    finally:
        safe_stop(base)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())
