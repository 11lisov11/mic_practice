"""Offline gates: coordinated reset cannot run on an armed or energized pair."""
import inspect
import json

import reset_unoq_nucleo_idle as reset


def main():
    checks = 0

    def check(v):
        nonlocal checks
        assert v
        checks += 1

    good = {"fw_build": 2026101001, "mc_fw_build": 2026100801,
            "state": "SAFE", "pwm": 0, "hmi_hv_armed": 0, "bp_status": 8,
            "bp_vbus_valid": 1, "vdc": 0.0, "bp_vbus_raw": 0,
            "mc_age_ms": 20, "bp_vbus_age_ms": 20,
            "precharge": 0, "pfc": 0, "brake": 0, "bp_ext": 0}
    check(reset.reset_safe(good))
    check(reset.reset_safe(dict(good, estop=1, mc_bad_cnt=1)))
    for key in good:
        missing = dict(good)
        del missing[key]
        check(not reset.reset_safe(missing))
    for key, value in (
        ("fw_build", 2026101002), ("mc_fw_build", 2026100899), ("state", "VF_RUN"),
        ("pwm", 1), ("hmi_hv_armed", 1), ("bp_status", 0x20), ("bp_status", 0x02),
        ("bp_vbus_valid", 0), ("vdc", 2.01), ("vdc", -1), ("vdc", float("nan")),
        ("bp_vbus_raw", 21), ("mc_age_ms", 300), ("bp_vbus_age_ms", 300),
        ("precharge", 1), ("pfc", 1), ("brake", 1), ("bp_ext", 1)):
        check(not reset.reset_safe(dict(good, **{key: value})))
    source = inspect.getsource(reset.main)
    check('"openocd_cfg=verify_unoq_sketch.cfg"' in source)
    check('"-w"' not in source and '"-w32"' not in source)
    check(source.index('"before_reset.json"') < source.index('run_logged(command'))
    check('"arm_commands": 0, "start_commands": 0' in source)
    check('"/api/start-sequence"' not in source and '"/api/hv-arm"' not in source)
    print(json.dumps({"pass": True, "checks": checks, "hardware_commands": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
