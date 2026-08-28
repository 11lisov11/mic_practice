#!/usr/bin/env python3
from __future__ import annotations

import json

import capture_as5600_teacher_dataset as capture


def main() -> int:
    good = {
        "pwm": 1, "freq": 10.0, "freq_cmd": 10.0, "speed": 600.0,
        "bp_vdc": 311.5, "ia": 0.2, "ib": -0.1, "ic": -0.1,
        "enc_ok": 1, "enc_raw": 2048, "enc_deg": 180.0, "enc_rpm": 600.0,
        "bp_status": 0x21, "bp_fault": 0, "bp_bad_cnt": 0,
        "bp_rsp_age_ms": 20, "bp_softstart_ready": 1,
        "precharge": 0, "bp_ext": 0,
    }
    sample = capture.normalize_sample(good, t_s=1.25, wall_time_ns=7, run_id="test", stage="S3")
    cases = {
        "good_status_accepted": capture.safety_error(good, require_pwm=True) is None,
        "angle_preserved": sample["enc_raw"] == 2048 and sample["enc_deg"] == 180.0,
        "fault_rejected": capture.safety_error(dict(good, bp_fault=3), require_pwm=True) == "motor controller fault=3",
        "legacy_relay_bit_rejected": capture.safety_error(dict(good, bp_ext=8), require_pwm=True) == "reserved precharge relay bit is nonzero",
        "stale_link_rejected": capture.safety_error(dict(good, bp_rsp_age_ms=501), require_pwm=True) == "motor-controller telemetry is stale",
        "missing_pwm_rejected": capture.safety_error(dict(good, pwm=0), require_pwm=True) == "PWM is not active",
    }
    result = {"tool": "capture_as5600_teacher_dataset_selftest", "pass": all(cases.values()), "cases": cases}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
