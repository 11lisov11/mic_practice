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


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def urlopen_direct(req_or_url, timeout_s: float):
    opener = request.build_opener(request.ProxyHandler({}))
    return opener.open(req_or_url, timeout=timeout_s)


def http_get_json(url: str, timeout_s: float) -> dict:
    with urlopen_direct(url, timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def status(base_url: str, timeout_s: float) -> dict:
    payload = http_get_json(base_url.rstrip("/") + "/api/status", timeout_s)
    if not payload.get("ok"):
        raise RuntimeError(f"status failed: {payload}")
    return payload["data"]


def as_float(v) -> float | None:
    try:
        if v is None:
            return None
        out = float(v)
        if not math.isfinite(out):
            return None
        return out
    except Exception:
        return None


def mean(vals: list[float]) -> float | None:
    return (sum(vals) / len(vals)) if vals else None


def stddev(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    mu = sum(vals) / len(vals)
    return math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1))


def summarize_key(samples: list[dict], key: str) -> dict:
    vals: list[float] = []
    for st in samples:
        v = as_float(st.get(key))
        if v is not None:
            vals.append(v)
    return {
        "key": key,
        "samples": len(vals),
        "mean": mean(vals),
        "std": stddev(vals),
        "min": min(vals) if vals else None,
        "max": max(vals) if vals else None,
    }


def as_int(v, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default


def sample_safe_for_zero_current(st: dict) -> bool:
    bp_bad_values = [as_int(st.get(key), 999999) for key in ("bp_bad_cnt", "bp_bad") if key in st]
    bp_bad = max(bp_bad_values) if bp_bad_values else 999999
    return (
        str(st.get("state", "")) == "SAFE"
        and as_int(st.get("pwm"), 1) == 0
        and as_int(st.get("estop"), 1) == 0
        and as_int(st.get("bp_fault"), 255) == 0
        and bp_bad == 0
    )


def zero_current_sanity(stats: dict, samples: list[dict], args) -> dict:
    safe_samples = [st for st in samples if sample_safe_for_zero_current(st)]
    phase_keys = ("ia", "ib", "ic")

    def stat_val(key: str, field: str) -> float | None:
        item = stats.get(key, {}) if isinstance(stats.get(key), dict) else {}
        return as_float(item.get(field))

    max_abs_mean = max([abs(stat_val(k, "mean") or 0.0) for k in phase_keys], default=0.0)
    max_abs_peak = 0.0
    for key in phase_keys:
        vals = [stat_val(key, "min"), stat_val(key, "max")]
        vals = [abs(v) for v in vals if v is not None]
        if vals:
            max_abs_peak = max(max_abs_peak, max(vals))
    i_rms_mean = stat_val("i_rms", "mean")
    i_rms_max = stat_val("i_rms", "max")

    checks = {
        "has_samples": len(samples) > 0,
        "all_samples_safe_pwm_off": len(samples) > 0 and len(safe_samples) == len(samples),
        "phase_mean_abs_ok": max_abs_mean <= float(args.max_zero_current_mean_a),
        "phase_peak_abs_ok": max_abs_peak <= float(args.max_zero_current_peak_a),
        "i_rms_mean_ok": (i_rms_mean is not None) and i_rms_mean <= float(args.max_zero_i_rms_mean_a),
        "i_rms_peak_ok": (i_rms_max is not None) and i_rms_max <= float(args.max_zero_i_rms_peak_a),
    }
    return {
        "enabled": not bool(args.skip_zero_current_check),
        "pass": True if args.skip_zero_current_check else all(checks.values()),
        "checks": checks,
        "safe_samples": len(safe_samples),
        "samples": len(samples),
        "thresholds": {
            "max_zero_current_mean_a": float(args.max_zero_current_mean_a),
            "max_zero_current_peak_a": float(args.max_zero_current_peak_a),
            "max_zero_i_rms_mean_a": float(args.max_zero_i_rms_mean_a),
            "max_zero_i_rms_peak_a": float(args.max_zero_i_rms_peak_a),
        },
        "metrics": {
            "max_abs_phase_mean_a": max_abs_mean,
            "max_abs_phase_peak_a": max_abs_peak,
            "i_rms_mean_a": i_rms_mean,
            "i_rms_peak_a": i_rms_max,
        },
    }


def vbus_calibration(zero_raw: float, cal_raw: float, cal_v: float) -> dict:
    denom = cal_raw - zero_raw
    if denom <= 1.0:
        raise ValueError(f"invalid Vbus calibration points: zero_raw={zero_raw} cal_raw={cal_raw}")
    scale = cal_v / denom
    return {
        "zero_raw": int(round(zero_raw)),
        "cal_raw": int(round(cal_raw)),
        "cal_v": float(cal_v),
        "scale_v_per_lsb": float(scale),
    }


def temp_tso_calibration(raw: float, known_temp_c: float, slope_mv_per_c: float, vref: float) -> dict:
    voltage = raw * vref / 4095.0
    tso_v25 = voltage - ((known_temp_c - 25.0) * slope_mv_per_c / 1000.0)
    return {
        "raw": float(raw),
        "voltage": float(voltage),
        "known_temp_c": float(known_temp_c),
        "tso_v25": float(tso_v25),
        "slope_mv_per_c": float(slope_mv_per_c),
    }


def format_config_patch(vbus: dict | None, temp: dict | None) -> str:
    lines: list[str] = []
    lines.append("// Suggested calibration constants. Review before committing/flashing.")
    if vbus:
        lines.append("// Blue Pill: bluepill_uart_pwm_pio/include/config.h")
        lines.append(f"#define ADC_VBUS_ZERO_RAW {vbus['zero_raw']}U")
        lines.append(f"#define ADC_VBUS_CAL_RAW {vbus['cal_raw']}U")
        lines.append(f"#define ADC_VBUS_CAL_V {vbus['cal_v']:.3f}f")
        lines.append(
            "#define ADC_VBUS_SCALE "
            f"({vbus['cal_v']:.3f}f / ((float)ADC_VBUS_CAL_RAW - (float)ADC_VBUS_ZERO_RAW))"
        )
        lines.append("")
        lines.append("// UNO Q mirror: UNOQ_MOTOR/UNOQ_MOTOR.ino")
        lines.append(f"static const uint16_t BP_VBUS_ZERO_RAW = {vbus['zero_raw']}U;")
        lines.append(f"static const uint16_t BP_VBUS_CAL_RAW = {vbus['cal_raw']}U;")
        lines.append(f"static const float BP_VBUS_CAL_V = {vbus['cal_v']:.3f}f;")
    if temp:
        if lines:
            lines.append("")
        lines.append("// TSO temperature calibration, if UM2014 SW3 remains in TSO mode.")
        lines.append("// Blue Pill: bluepill_uart_pwm_pio/include/config.h")
        lines.append(f"#define HEATSINK_TEMP_TSO_V25 {temp['tso_v25']:.5f}f")
        lines.append(f"#define HEATSINK_TEMP_TSO_MV_PER_C {temp['slope_mv_per_c']:.3f}f")
        lines.append("")
        lines.append("// UNO Q mirror: UNOQ_MOTOR/UNOQ_MOTOR.ino")
        lines.append(f"static const float BP_TEMP_TSO_V25 = {temp['tso_v25']:.5f}f;")
        lines.append(f"static const float BP_TEMP_TSO_MV_PER_C = {temp['slope_mv_per_c']:.3f}f;")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Capture telemetry calibration snapshots and compute suggested constants.")
    ap.add_argument("--url", default="http://127.0.0.1:18080")
    ap.add_argument("--samples", type=int, default=60)
    ap.add_argument("--poll", type=float, default=0.05)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--outdir", default="tools/_calibration_exports")
    ap.add_argument("--tag", default="telemetry_calibration")
    ap.add_argument("--allow-hv", action="store_true", help="Allow capture/computation above 60 V.")
    ap.add_argument("--meter-vdc", type=float, default=None, help="Known external meter Vdc for current capture/cal point.")
    ap.add_argument("--vbus-zero-raw", type=float, default=None, help="Bus-off raw ADC point from a previous zero capture.")
    ap.add_argument("--vbus-cal-raw", type=float, default=None, help="Known-voltage raw ADC point for offline calculation.")
    ap.add_argument("--known-temp-c", type=float, default=None, help="Known heatsink temperature for TSO V25 calibration.")
    ap.add_argument("--temp-slope-mv-per-c", type=float, default=18.0)
    ap.add_argument("--temp-vref", type=float, default=3.3)
    ap.add_argument("--skip-zero-current-check", action="store_true", help="Do not fail when SAFE zero-current telemetry is outside thresholds.")
    ap.add_argument("--max-zero-current-mean-a", type=float, default=1.0, help="Max accepted abs(mean ia/ib/ic) in SAFE/pwm=0.")
    ap.add_argument("--max-zero-current-peak-a", type=float, default=2.0, help="Max accepted abs(min/max ia/ib/ic) in SAFE/pwm=0.")
    ap.add_argument("--max-zero-i-rms-mean-a", type=float, default=1.0, help="Max accepted mean i_rms in SAFE/pwm=0.")
    ap.add_argument("--max-zero-i-rms-peak-a", type=float, default=2.0, help="Max accepted max i_rms in SAFE/pwm=0.")
    args = ap.parse_args()

    out_root = Path(args.outdir).resolve()
    run_dir = out_root / f"{args.tag}_{ts_tag()}"
    run_dir.mkdir(parents=True, exist_ok=True)

    samples: list[dict] = []
    online_error = None
    try:
        for _ in range(max(1, int(args.samples))):
            st = status(args.url, args.timeout)
            samples.append(st)
            time.sleep(max(0.0, float(args.poll)))
    except Exception as exc:
        online_error = str(exc)

    summary_keys = [
        "bp_vbus_raw",
        "bp_vdc",
        "bp_temp_raw",
        "bp_temp_v",
        "bp_temp_c",
        "bp_phase_a_raw",
        "bp_phase_b_raw",
        "bp_phase_c_raw",
        "ia",
        "ib",
        "ic",
        "i_rms",
        "bp_fan_rpm",
    ]
    stats = {key: summarize_key(samples, key) for key in summary_keys}
    zero_current = zero_current_sanity(stats, samples, args)

    current_vdc = max([float(st.get("bp_vdc", 0.0) or 0.0) for st in samples], default=0.0)
    requested_vdc = float(args.meter_vdc or 0.0)
    if (current_vdc > 60.0 or requested_vdc > 60.0) and not args.allow_hv:
        result = {
            "tool": "telemetry_calibration",
            "run_metadata": collect_run_metadata(Path(__file__).resolve().parents[1]),
            "pass": False,
            "error": "HV-like Vbus detected/requested; rerun with --allow-hv if the bench is intentionally energized",
            "max_status_vdc": current_vdc,
            "meter_vdc": args.meter_vdc,
            "stats": stats,
            "zero_current_sanity": zero_current,
            "online_error": online_error,
        }
        (run_dir / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"pass": False, "summary": str(run_dir / "summary.json"), "error": result["error"]}, ensure_ascii=False))
        return 2

    vbus = None
    zero_raw = args.vbus_zero_raw
    cal_raw = args.vbus_cal_raw
    if cal_raw is None and samples:
        cal_raw = stats["bp_vbus_raw"]["mean"]
    if args.meter_vdc is not None and zero_raw is not None and cal_raw is not None:
        vbus = vbus_calibration(float(zero_raw), float(cal_raw), float(args.meter_vdc))

    temp = None
    temp_raw = stats["bp_temp_raw"]["mean"]
    if args.known_temp_c is not None and temp_raw is not None:
        temp = temp_tso_calibration(float(temp_raw), float(args.known_temp_c), float(args.temp_slope_mv_per_c), float(args.temp_vref))

    result = {
        "tool": "telemetry_calibration",
        "run_metadata": collect_run_metadata(Path(__file__).resolve().parents[1]),
        "url": args.url,
        "samples_requested": int(args.samples),
        "samples_collected": len(samples),
        "online_error": online_error,
        "stats": stats,
        "zero_current_sanity": zero_current,
        "vbus_calibration": vbus,
        "temp_tso_calibration": temp,
        "notes": [
            "Vbus calibration uses raw ADC points, not current bp_vdc scaling.",
            "Current raw ADC values are not exposed in the current telemetry protocol; current calibration still requires firmware/protocol extension or external instrumentation.",
            "Zero-current sanity is evaluated from SAFE/pwm=0 ia/ib/ic/i_rms telemetry; use --skip-zero-current-check only for non-zero-current captures.",
            "Use --allow-hv only when the bench is intentionally energized and externally protected.",
        ],
    }
    result["pass"] = bool(online_error is None and len(samples) > 0 and zero_current.get("pass") is True)
    patch_text = format_config_patch(vbus, temp)
    (run_dir / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "suggested_constants.txt").write_text(patch_text, encoding="utf-8")
    print(json.dumps({"pass": result["pass"], "summary": str(run_dir / "summary.json"), "suggested_constants": str(run_dir / "suggested_constants.txt")}, ensure_ascii=False))
    return 0 if result["pass"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
