from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_module():
    path = Path(__file__).with_name("unoq_wifi_hmi_deploy.py")
    spec = importlib.util.spec_from_file_location("unoq_wifi_hmi_deploy_under_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Wi-Fi HMI deploy module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status(**overrides):
    value = {
        "state": "SAFE",
        "pwm": 0,
        "estop": 0,
        "precharge": 0,
        "pfc": 0,
        "brake": 0,
        "bp_fault": 0,
        "bp_bad": 0,
        "bp_bad_cnt": 0,
        "bp_rsp_age_ms": 25,
        "bp_vbus_age_ms": 25,
        "bp_vbus_raw": 120,
        "vdc": 0.0,
        "bp_vdc": 0.0,
    }
    value.update(overrides)
    return value


def main() -> int:
    mod = load_module()
    cases = []

    def check(name, expected, data):
        ok, reason = mod.safe_for_update(data, 10.0)
        passed = ok is expected
        cases.append({"name": name, "ok": passed, "result": ok, "reason": reason})

    check("accept_safe_zero_bus", True, status())
    check("reject_running", False, status(state="VF_RUN", pwm=1))
    check("reject_relay_on", False, status(precharge=1))
    check("reject_fault", False, status(bp_fault=6))
    check("reject_bad_uart", False, status(bp_bad_cnt=1))
    check("reject_stale_link", False, status(bp_rsp_age_ms=5000))
    check("reject_high_secondary_vbus", False, status(vdc=0.0, bp_vdc=315.0))
    check("reject_high_raw_vbus_with_zero_scaled", False, status(bp_vbus_raw=3256))
    check("reject_missing_raw_vbus", False, {key: value for key, value in status().items() if key != "bp_vbus_raw"})
    check("reject_stale_raw_vbus", False, status(bp_vbus_age_ms=5000))
    check("reject_invalid_raw_vbus", False, status(bp_vbus_raw=0))
    check("reject_missing_vbus", False, {key: value for key, value in status().items() if key not in ("vdc", "bp_vdc")})
    check("reject_invalid_output_telemetry", False, status(pwm="invalid"))

    failed = [case for case in cases if not case["ok"]]
    print(json.dumps({"pass": not failed, "passed": len(cases) - len(failed), "failed": len(failed), "cases": cases}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
