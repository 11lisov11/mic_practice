#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
import urllib.request
from pathlib import Path
from typing import Any


FIELDS = (
    "t_s", "wall_time_ns", "run_id", "stage", "pwm", "freq_cmd_hz",
    "freq_ref_hz", "speed_cmd_rpm", "vbus_v", "ia_a", "ib_a", "ic_a",
    "id_a", "iq_a", "enc_ok", "enc_raw", "enc_deg", "enc_rpm",
    "enc_mech_hz", "enc_elec_hz", "bp_status", "bp_fault", "bp_bad",
    "bp_rsp_age_ms", "softstart_ready",
)


def number(data: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = float(data.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def normalize_sample(data: dict[str, Any], *, t_s: float, wall_time_ns: int,
                     run_id: str, stage: str) -> dict[str, Any]:
    return {
        "t_s": round(t_s, 9),
        "wall_time_ns": int(wall_time_ns),
        "run_id": run_id,
        "stage": stage,
        "pwm": int(number(data, "pwm")),
        "freq_cmd_hz": number(data, "freq_cmd", number(data, "freq")),
        "freq_ref_hz": number(data, "freq"),
        "speed_cmd_rpm": number(data, "speed"),
        "vbus_v": number(data, "bp_vdc", number(data, "vdc")),
        "ia_a": number(data, "ia"),
        "ib_a": number(data, "ib"),
        "ic_a": number(data, "ic"),
        "id_a": number(data, "id"),
        "iq_a": number(data, "iq"),
        "enc_ok": int(number(data, "enc_ok")),
        "enc_raw": int(number(data, "enc_raw", -1.0)),
        "enc_deg": number(data, "enc_deg"),
        "enc_rpm": number(data, "enc_rpm"),
        "enc_mech_hz": number(data, "enc_mech_hz"),
        "enc_elec_hz": number(data, "enc_elec_hz"),
        "bp_status": int(number(data, "bp_status")),
        "bp_fault": int(number(data, "bp_fault", 255.0)),
        "bp_bad": int(number(data, "bp_bad_cnt", number(data, "bp_bad", 0.0))),
        "bp_rsp_age_ms": int(number(data, "bp_rsp_age_ms", 999999.0)),
        "softstart_ready": int(number(data, "bp_softstart_ready")),
    }


def safety_error(data: dict[str, Any], *, require_pwm: bool) -> str | None:
    if int(number(data, "precharge")) != 0 or (int(number(data, "bp_ext")) & 0x08):
        return "reserved precharge relay bit is nonzero"
    if int(number(data, "bp_fault", 255.0)) != 0:
        return f"motor controller fault={int(number(data, 'bp_fault', 255.0))}"
    if int(number(data, "bp_rsp_age_ms", 999999.0)) > 500:
        return "motor-controller telemetry is stale"
    if require_pwm and int(number(data, "pwm")) != 1:
        return "PWM is not active"
    return None


def get_status(base_url: str, timeout: float) -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base_url.rstrip("/") + "/api/status", timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok") or not isinstance(payload.get("data"), dict):
        raise RuntimeError("HMI returned no status data")
    return payload["data"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture AS5600 teacher labels with motor telemetry")
    parser.add_argument("--url", default="http://127.0.0.1:18080")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--poll", type=float, default=0.02)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", default="manual")
    parser.add_argument("--stage", default="S3_AS5600_TEACHER")
    parser.add_argument("--min-valid-ratio", type=float, default=0.98)
    parser.add_argument("--require-pwm", action="store_true")
    args = parser.parse_args()

    duration = max(0.2, args.duration)
    poll = max(0.005, args.poll)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    samples = 0
    valid = 0
    start = time.monotonic()
    failure = ""

    try:
        with temp.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            while time.monotonic() - start < duration:
                status = get_status(args.url, args.timeout)
                failure = safety_error(status, require_pwm=args.require_pwm) or ""
                if failure:
                    raise RuntimeError(failure)
                sample = normalize_sample(
                    status,
                    t_s=time.monotonic() - start,
                    wall_time_ns=time.time_ns(),
                    run_id=args.run_id,
                    stage=args.stage,
                )
                writer.writerow(sample)
                samples += 1
                valid += int(sample["enc_ok"] == 1 and 0 <= sample["enc_raw"] <= 4095)
                time.sleep(poll)
        ratio = valid / samples if samples else 0.0
        if samples == 0 or ratio < max(0.0, min(1.0, args.min_valid_ratio)):
            raise RuntimeError(f"AS5600 valid ratio {ratio:.4f} is below the acceptance limit")
        temp.replace(output)
    except Exception as exc:
        temp.unlink(missing_ok=True)
        print(f"FAIL: {exc}")
        return 2

    metadata = {
        "schema": "mic_ai.as5600_teacher_dataset.v1",
        "csv": output.name,
        "sha256": sha256(output),
        "samples": samples,
        "valid_samples": valid,
        "valid_ratio": valid / samples,
        "duration_s": time.monotonic() - start,
        "poll_requested_s": poll,
        "run_id": args.run_id,
        "stage": args.stage,
        "require_pwm": args.require_pwm,
    }
    metadata_path = output.with_suffix(output.suffix + ".json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
