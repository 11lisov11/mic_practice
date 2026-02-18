#!/usr/bin/env python3
import argparse
import json
import sys
import time
import urllib.request
from dataclasses import dataclass


def log(msg: str) -> None:
    print(msg, flush=True)


def http_json(url: str, timeout: float) -> dict | None:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except Exception as exc:
        log(f"HTTP error: {exc}")
        return None


def get_status(base: str, timeout: float) -> dict | None:
    resp = http_json(base + "/api/status", timeout=timeout)
    if not resp or not resp.get("ok"):
        return None
    return resp.get("data")


@dataclass
class Sample:
    t_s: float
    enc_ok: int
    raw: int
    deg: float


def main() -> int:
    p = argparse.ArgumentParser(description="AS5600 encoder position sampling via UNOQ /api/status")
    p.add_argument("--url", default="http://127.0.0.1:18080", help="Base URL for UNOQ web_hmi")
    p.add_argument("--duration", type=float, default=10.0, help="Seconds to sample (finite)")
    p.add_argument("--poll", type=float, default=0.05, help="Polling interval seconds")
    p.add_argument("--timeout", type=float, default=0.4, help="HTTP timeout seconds")
    args = p.parse_args()

    base = args.url.rstrip("/")
    dur = max(0.2, float(args.duration))
    poll = max(0.01, float(args.poll))

    log(f"START encoder_test duration={dur:.2f}s poll={poll:.3f}s url={base}")
    log("Columns: t_s enc_ok enc_raw enc_deg")

    start = time.monotonic()
    samples: list[Sample] = []

    while (time.monotonic() - start) < dur:
        st = get_status(base, timeout=args.timeout)
        if st is None:
            time.sleep(poll)
            continue
        ok_v = st.get("enc_ok", 0)
        raw_v = st.get("enc_raw", -1)
        deg_v = st.get("enc_deg", 0.0)
        ok = int(0 if ok_v is None else ok_v)
        raw = int(-1 if raw_v is None else raw_v)
        deg = float(0.0 if deg_v is None else deg_v)
        t_s = time.monotonic() - start
        samples.append(Sample(t_s=t_s, enc_ok=ok, raw=raw, deg=deg))
        log(f"{t_s:7.3f} {ok:6d} {raw:7d} {deg:9.3f}")
        time.sleep(poll)

    if not samples:
        log("FAIL: no samples received (check ADB forward and web_hmi)")
        return 2

    oks = sum(s.enc_ok for s in samples)
    raws = [s.raw for s in samples if s.raw >= 0]
    degs = [s.deg for s in samples]

    # Movement estimate with wrap handling (12-bit, 0..4095).
    wraps_fwd = 0
    wraps_rev = 0
    delta_counts = 0
    for a, b in zip(samples, samples[1:]):
        dr = b.raw - a.raw
        if dr < -2000:
            wraps_fwd += 1
            dr += 4096
        elif dr > 2000:
            wraps_rev += 1
            dr -= 4096
        delta_counts += dr

    moved_deg = (delta_counts / 4096.0) * 360.0
    span_raw = (max(raws) - min(raws)) if raws else 0
    span_deg = (max(degs) - min(degs)) if degs else 0.0

    log("---")
    log(f"samples={len(samples)} enc_ok_ratio={oks/len(samples):.3f}")
    if raws:
        log(f"raw_now={raws[-1]} raw_min={min(raws)} raw_max={max(raws)} raw_span={span_raw}")
    log(f"deg_now={degs[-1]:.3f} deg_min={min(degs):.3f} deg_max={max(degs):.3f} deg_span={span_deg:.3f}")
    log(f"wraps_fwd={wraps_fwd} wraps_rev={wraps_rev} moved_deg_est={moved_deg:.2f}")

    if oks == 0:
        log("FAIL: enc_ok stayed 0 for all samples (I2C read failed). Check PB10/PB11 wiring and 3.3V power.")
        return 3

    if span_raw <= 2:
        log("NOTE: encoder angle did not change (shaft/magnet likely stationary during test).")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    raise SystemExit(main())
