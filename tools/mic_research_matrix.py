#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib import request

from run_metadata import collect_run_metadata


def ts_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def parse_float_list(text: str) -> list[float]:
    out: list[float] = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        out.append(float(token))
    if not out:
        raise ValueError("empty frequency list")
    return out


def load_json_object(path_text: str) -> dict:
    path = Path(path_text)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def build_bench_context(args) -> dict:
    context: dict = {}
    if args.bench_config:
        context.update(load_json_object(args.bench_config))
        context["bench_config_path"] = str(Path(args.bench_config).resolve())
    explicit = {
        "operator": args.operator,
        "motor_label": args.motor_label,
        "load_note": args.load_note,
        "supply_note": args.supply_note,
        "instrumentation_note": args.instrumentation_note,
        "bench_note": args.bench_note,
    }
    for key, value in explicit.items():
        if value:
            context[key] = value
    if args.ambient_c is not None:
        context["ambient_c"] = float(args.ambient_c)
    return context


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


def safe_stop(base_url: str, timeout_s: float) -> None:
    for cmd in ("STOP", "FAN OFF"):
        try:
            http_post_cmd(base_url, cmd, timeout_s)
        except Exception:
            pass


def st_int(st: dict, key: str, default: int) -> int:
    try:
        return int(st.get(key, default))
    except Exception:
        return default


def st_float(st: dict, *keys: str) -> float | None:
    for key in keys:
        value = st.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


def status_vdc(st: dict) -> float | None:
    return st_float(st, "vdc", "bp_vdc", "vbus", "dc_bus_v", "dc_bus_voltage")


def status_safe_for_start(
    st: dict,
    *,
    require_encoder: bool = False,
    allow_hv: bool = False,
    max_start_vdc: float = 60.0,
) -> tuple[bool, str]:
    if st.get("state") != "SAFE":
        return False, f"state is {st.get('state')}, expected SAFE"
    if st_int(st, "pwm", 1) != 0:
        return False, "pwm is not 0"
    if st_int(st, "estop", 1) != 0:
        return False, "estop is latched"
    if st_int(st, "bp_fault", 255) != 0:
        return False, f"bp_fault={st.get('bp_fault')}"
    bp_bad_values = [st_int(st, key, 999999) for key in ("bp_bad_cnt", "bp_bad") if key in st]
    bp_bad = max(bp_bad_values) if bp_bad_values else 999999
    if bp_bad != 0:
        return False, f"bp_bad={bp_bad}"
    if require_encoder and st_int(st, "enc_ok", 0) != 1:
        return False, f"enc_ok={st.get('enc_ok')}, expected 1"
    vdc = status_vdc(st)
    if not allow_hv:
        if vdc is None:
            return False, "vdc is not readable; use --allow-hv only for an intentional HV run"
        if abs(vdc) > float(max_start_vdc):
            return (
                False,
                f"vdc={vdc:.1f} V exceeds max_start_vdc={float(max_start_vdc):.1f} V; "
                "remove/discharge HV or pass --allow-hv for an intentional HV run",
            )
    return True, "ok"


def newest_summary(raw_dir: Path, tag: str, before: set[Path]) -> Path | None:
    candidates = set(raw_dir.glob(f"{tag}_*/summary.json")) - before
    if not candidates:
        candidates = set(raw_dir.glob("*/summary.json")) - before
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def pct(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def compact_values(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ",".join(str(x) for x in v)
    return str(v)


def row_from_summary(freq: float, repeat_idx: int, rc: int, summary_path: Path | None, elapsed_s: float) -> dict:
    row: dict = {
        "freq_hz": freq,
        "repeat": repeat_idx,
        "returncode": rc,
        "elapsed_s": round(elapsed_s, 3),
        "summary": str(summary_path) if summary_path else "",
        "pass": False,
    }
    if not summary_path or not summary_path.exists():
        row["error"] = "missing_summary"
        return row
    data = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    foc = data.get("foc", {})
    mic = data.get("mic", {})
    diff = data.get("diff", {})
    checks = data.get("checks", {})
    row.update(
        {
            "pass": bool(data.get("pass")) and rc == 0,
            "foc_i_rms": pct(foc.get("mean_i_rms")),
            "mic_i_rms": pct(mic.get("mean_i_rms")),
            "i_rms_pct": pct(diff.get("i_rms_pct")),
            "foc_p_proxy": pct(foc.get("mean_p_proxy")),
            "mic_p_proxy": pct(mic.get("mean_p_proxy")),
            "p_proxy_pct": pct(diff.get("p_proxy_pct")),
            "foc_enc_rpm": pct(foc.get("mean_enc_rpm")),
            "mic_enc_rpm": pct(mic.get("mean_enc_rpm")),
            "enc_rpm_pct": pct(diff.get("enc_rpm_pct")),
            "mic_active_ratio": pct(mic.get("mic_active_ratio")),
            "mic_gated_ratio": pct(mic.get("mic_gated_ratio")),
            "mic_saving_pct_mean": pct(mic.get("mean_mic_saving_pct")),
            "foc_enc_ok_ratio": pct(foc.get("enc_ok_ratio")),
            "mic_enc_ok_ratio": pct(mic.get("enc_ok_ratio")),
            "foc_bp_cmd_modes": compact_values(foc.get("bp_cmd_mode_values")),
            "mic_bp_cmd_modes": compact_values(mic.get("bp_cmd_mode_values")),
            "foc_bp_foc_backend": compact_values(foc.get("bp_foc_backend_values")),
            "mic_bp_foc_backend": compact_values(mic.get("bp_foc_backend_values")),
            "checks": json.dumps(checks, ensure_ascii=False, sort_keys=True),
        }
    )
    return row


def write_rows_csv(path: Path, rows: list[dict]) -> None:
    keys = [
        "freq_hz",
        "repeat",
        "returncode",
        "pass",
        "elapsed_s",
        "foc_i_rms",
        "mic_i_rms",
        "i_rms_pct",
        "foc_p_proxy",
        "mic_p_proxy",
        "p_proxy_pct",
        "foc_enc_rpm",
        "mic_enc_rpm",
        "enc_rpm_pct",
        "mic_active_ratio",
        "mic_gated_ratio",
        "mic_saving_pct_mean",
        "foc_enc_ok_ratio",
        "mic_enc_ok_ratio",
        "foc_bp_cmd_modes",
        "mic_bp_cmd_modes",
        "foc_bp_foc_backend",
        "mic_bp_foc_backend",
        "summary",
        "log",
        "error",
        "timeout_s",
        "timeout_error",
        "checks",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def aggregate(rows: list[dict], min_mic_active_ratio: float) -> dict:
    total = len(rows)
    passed = sum(1 for r in rows if bool(r.get("pass")))
    mic_active_vals = [float(r["mic_active_ratio"]) for r in rows if r.get("mic_active_ratio") is not None]
    p_proxy_vals = [float(r["p_proxy_pct"]) for r in rows if r.get("p_proxy_pct") is not None]
    i_rms_vals = [float(r["i_rms_pct"]) for r in rows if r.get("i_rms_pct") is not None]

    def mean(vals: list[float]) -> float | None:
        return (sum(vals) / len(vals)) if vals else None

    def stddev(vals: list[float]) -> float | None:
        if len(vals) < 2:
            return None
        mu = sum(vals) / len(vals)
        return math.sqrt(sum((v - mu) ** 2 for v in vals) / (len(vals) - 1))

    def metric_vals(group: list[dict], key: str) -> list[float]:
        vals: list[float] = []
        for row in group:
            v = row.get(key)
            if v is None or v == "":
                continue
            try:
                vals.append(float(v))
            except Exception:
                continue
        return vals

    by_freq: dict[str, dict] = {}
    for freq in sorted({float(r["freq_hz"]) for r in rows if r.get("freq_hz") is not None}):
        group = [r for r in rows if float(r.get("freq_hz", -1.0)) == freq]
        freq_key = f"{freq:g}"
        by_freq[freq_key] = {
            "runs_total": len(group),
            "runs_passed": sum(1 for r in group if bool(r.get("pass"))),
            "mic_active_ratio_mean": mean(metric_vals(group, "mic_active_ratio")),
            "mic_active_ratio_std": stddev(metric_vals(group, "mic_active_ratio")),
            "p_proxy_pct_mean": mean(metric_vals(group, "p_proxy_pct")),
            "p_proxy_pct_std": stddev(metric_vals(group, "p_proxy_pct")),
            "i_rms_pct_mean": mean(metric_vals(group, "i_rms_pct")),
            "i_rms_pct_std": stddev(metric_vals(group, "i_rms_pct")),
            "enc_rpm_pct_mean": mean(metric_vals(group, "enc_rpm_pct")),
            "enc_rpm_pct_std": stddev(metric_vals(group, "enc_rpm_pct")),
        }

    return {
        "runs_total": total,
        "runs_passed": passed,
        "runs_failed": total - passed,
        "all_passed": passed == total and total > 0,
        "min_mic_active_ratio": min(mic_active_vals) if mic_active_vals else None,
        "mean_mic_active_ratio": mean(mic_active_vals),
        "std_mic_active_ratio": stddev(mic_active_vals),
        "mean_p_proxy_pct": mean(p_proxy_vals),
        "std_p_proxy_pct": stddev(p_proxy_vals),
        "mean_i_rms_pct": mean(i_rms_vals),
        "std_i_rms_pct": stddev(i_rms_vals),
        "by_freq": by_freq,
        "research_ready": (passed == total and total > 0 and bool(mic_active_vals) and min(mic_active_vals) >= min_mic_active_ratio),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run repeated FOC vs MIC experiments and aggregate scientific evidence.")
    ap.add_argument("--url", default="http://127.0.0.1:18080")
    ap.add_argument("--freqs", default="2,5,10,20", help="comma-separated electrical Hz commands")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--duration", type=float, default=10.0)
    ap.add_argument("--warmup", type=float, default=1.0)
    ap.add_argument("--poll", type=float, default=0.05)
    ap.add_argument("--status-timeout", type=float, default=1.5)
    ap.add_argument(
        "--case-timeout-s",
        type=float,
        default=0.0,
        help="Timeout for each mic_ai_compare subprocess; 0 = auto from duration/warmup/status timeout.",
    )
    ap.add_argument("--settle", type=float, default=1.0)
    ap.add_argument("--outdir", default="tools/_research_exports")
    ap.add_argument("--tag", default="mic_matrix")
    ap.add_argument("--require-encoder", action="store_true")
    ap.add_argument("--continue-on-fail", action="store_true")
    ap.add_argument("--allow-hv", action="store_true", help="Allow matrix START when measured Vbus is above --max-start-vdc.")
    ap.add_argument("--max-start-vdc", type=float, default=60.0, help="Low-voltage START guard threshold.")
    ap.add_argument("--start-vdc-samples", type=int, default=3, help="Vbus samples passed to each mic_ai_compare START guard.")
    ap.add_argument("--min-mic-active-ratio", type=float, default=0.05)
    ap.add_argument("--max-i-rms-increase-pct", type=float, default=2.0)
    ap.add_argument("--max-p-proxy-increase-pct", type=float, default=3.0)
    ap.add_argument("--max-enc-rpm-delta-pct", type=float, default=8.0)
    ap.add_argument("--min-enc-rpm-for-speed-check", type=float, default=50.0)
    ap.add_argument("--min-mic-saving-pct", type=float, default=0.0)
    ap.add_argument("--bench-config", default="", help="Optional JSON object with bench/motor/load/instrumentation context.")
    ap.add_argument("--operator", default="", help="Optional operator/lab identifier for reproducibility.")
    ap.add_argument("--motor-label", default="", help="Motor label/nameplate identifier.")
    ap.add_argument("--load-note", default="", help="Load condition note, e.g. no-load, fan load, brake setting.")
    ap.add_argument("--supply-note", default="", help="Supply condition note, e.g. 315 VDC bus, current limit, fuse.")
    ap.add_argument("--instrumentation-note", default="", help="Oscilloscope/Saleae/meter notes relevant to the run.")
    ap.add_argument("--ambient-c", type=float, default=None, help="Ambient temperature in deg C.")
    ap.add_argument("--bench-note", default="", help="Free-form bench condition note.")
    args = ap.parse_args()

    base = args.url.rstrip("/")
    freqs = parse_float_list(args.freqs)
    repeats = max(1, int(args.repeats))
    bench_context = build_bench_context(args)
    case_timeout_s = (
        float(args.case_timeout_s)
        if float(args.case_timeout_s) > 0.0
        else max(
            300.0,
            (float(args.duration) * 8.0)
            + (float(args.warmup) * 8.0)
            + (float(args.status_timeout) * 20.0)
            + 60.0,
        )
    )
    start_vdc_samples = max(1, int(args.start_vdc_samples))
    out_root = Path(args.outdir).resolve()
    run_dir = out_root / f"{args.tag}_{ts_tag()}"
    raw_dir = run_dir / "raw"
    logs_dir = run_dir / "logs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "tool": "mic_research_matrix",
        "url": base,
        "run_metadata": collect_run_metadata(Path(__file__).resolve().parents[1]),
        "freqs": freqs,
        "repeats": repeats,
        "duration": args.duration,
        "warmup": args.warmup,
        "poll": args.poll,
        "case_timeout_s": case_timeout_s,
        "allow_hv": bool(args.allow_hv),
        "max_start_vdc": float(args.max_start_vdc),
        "start_vdc_samples": start_vdc_samples,
        "bench_context": bench_context,
        "run_dir": str(run_dir),
        "rows": [],
    }

    try:
        st = status(base, args.status_timeout)
        result["initial_status"] = st
        safe, reason = status_safe_for_start(
            st,
            require_encoder=bool(args.require_encoder),
            allow_hv=bool(args.allow_hv),
            max_start_vdc=float(args.max_start_vdc),
        )
        if not safe:
            result["precondition_error"] = reason
            (run_dir / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps({"pass": False, "reason": reason, "summary": str(run_dir / "summary.json")}, ensure_ascii=False))
            return 2

        for freq in freqs:
            for repeat_idx in range(1, repeats + 1):
                tag = f"{args.tag}_{freq:.1f}Hz_r{repeat_idx}".replace(".", "p")
                before = set(raw_dir.glob("*/summary.json"))
                st = status(base, args.status_timeout)
                result["last_pre_case_status"] = st
                safe, reason = status_safe_for_start(
                    st,
                    require_encoder=bool(args.require_encoder),
                    allow_hv=bool(args.allow_hv),
                    max_start_vdc=float(args.max_start_vdc),
                )
                if not safe:
                    row = {
                        "freq_hz": freq,
                        "repeat": repeat_idx,
                        "returncode": 2,
                        "pass": False,
                        "elapsed_s": 0.0,
                        "error": "precondition_failed",
                        "timeout_s": "",
                        "timeout_error": reason,
                    }
                    result["rows"].append(row)
                    result["precondition_error"] = reason
                    result["aggregate"] = aggregate(result["rows"], float(args.min_mic_active_ratio))
                    write_rows_csv(run_dir / "aggregate.csv", result["rows"])
                    (run_dir / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
                    print(json.dumps({"pass": False, "reason": reason, "summary": str(run_dir / "summary.json")}, ensure_ascii=False))
                    return 2
                cmd = [
                    sys.executable,
                    str(Path(__file__).with_name("mic_ai_compare.py")),
                    "--url",
                    base,
                    "--freq",
                    f"{freq:.2f}",
                    "--duration",
                    f"{float(args.duration):.3f}",
                    "--warmup",
                    f"{float(args.warmup):.3f}",
                    "--poll",
                    f"{float(args.poll):.3f}",
                    "--status-timeout",
                    f"{float(args.status_timeout):.3f}",
                    "--outdir",
                    str(raw_dir),
                    "--tag",
                    tag,
                    "--min-mic-active-ratio",
                    f"{float(args.min_mic_active_ratio):.4f}",
                    "--max-i-rms-increase-pct",
                    f"{float(args.max_i_rms_increase_pct):.3f}",
                    "--max-p-proxy-increase-pct",
                    f"{float(args.max_p_proxy_increase_pct):.3f}",
                    "--max-enc-rpm-delta-pct",
                    f"{float(args.max_enc_rpm_delta_pct):.3f}",
                    "--min-enc-rpm-for-speed-check",
                    f"{float(args.min_enc_rpm_for_speed_check):.3f}",
                    "--min-mic-saving-pct",
                    f"{float(args.min_mic_saving_pct):.3f}",
                    "--max-start-vdc",
                    f"{float(args.max_start_vdc):.3f}",
                    "--start-vdc-samples",
                    str(start_vdc_samples),
                ]
                if args.require_encoder:
                    cmd.append("--require-encoder")
                if args.allow_hv:
                    cmd.append("--allow-hv")
                log_path = logs_dir / f"{tag}.log"
                start = time.monotonic()
                timed_out = False
                timeout_error = ""
                with log_path.open("w", encoding="utf-8") as log_f:
                    try:
                        proc = subprocess.run(
                            cmd,
                            cwd=Path(__file__).resolve().parents[1],
                            stdout=log_f,
                            stderr=subprocess.STDOUT,
                            timeout=case_timeout_s,
                        )
                        rc = proc.returncode
                    except subprocess.TimeoutExpired as exc:
                        timed_out = True
                        timeout_error = f"timeout after {case_timeout_s:.1f}s: {exc.cmd}"
                        log_f.write("\n[TIMEOUT]\n")
                        log_f.write(timeout_error + "\n")
                        rc = 124
                elapsed_s = time.monotonic() - start
                summary_path = newest_summary(raw_dir, tag, before)
                row = row_from_summary(freq, repeat_idx, rc, summary_path, elapsed_s)
                row["log"] = str(log_path)
                if timed_out:
                    row["error"] = "timeout"
                    row["timeout_s"] = round(case_timeout_s, 3)
                    row["timeout_error"] = timeout_error
                result["rows"].append(row)
                write_rows_csv(run_dir / "aggregate.csv", result["rows"])
                result["aggregate"] = aggregate(result["rows"], float(args.min_mic_active_ratio))
                (run_dir / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

                safe_stop(base, args.status_timeout)
                time.sleep(max(0.0, float(args.settle)))
                if rc != 0 and not args.continue_on_fail:
                    print(json.dumps({"pass": False, "failed": row, "summary": str(run_dir / "summary.json")}, ensure_ascii=False))
                    return rc or 1
    finally:
        safe_stop(base, args.status_timeout)

    result["aggregate"] = aggregate(result["rows"], float(args.min_mic_active_ratio))
    write_rows_csv(run_dir / "aggregate.csv", result["rows"])
    (run_dir / "summary.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    ok = bool(result["aggregate"].get("research_ready"))
    print(json.dumps({"pass": ok, "aggregate": result["aggregate"], "summary": str(run_dir / "summary.json")}, ensure_ascii=False))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
