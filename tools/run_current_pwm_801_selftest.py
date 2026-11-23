"""Offline safety gates for the isolated current-firmware PWM runner."""
import inspect
import json

import run_current_pwm_801 as bench


def main():
    checks = 0

    def check(value):
        nonlocal checks
        assert value
        checks += 1

    s = {"state": "SAFE", "pwm": 0, "fw_build": 2026101001,
         "hmi_hv_armed": 0, "vdc": 1.0, "bp_vbus_raw": 10,
         "bp_vbus_valid": 1, "bp_age_ms": 10, "bp_vbus_age_ms": 10,
         "bp_status": 0, "precharge": 0, "pfc": 0, "brake": 0, "bp_ext": 0}
    check(bench.isolated_idle(s, 2026101001))
    for key in s:
        missing = dict(s)
        del missing[key]
        check(not bench.isolated_idle(missing, 2026101001))
    for key, value in (
        ("state", "VF_RUN"), ("pwm", 1), ("fw_build", 2026101002),
        ("hmi_hv_armed", 1), ("vdc", 2.01), ("vdc", -1),
        ("vdc", float("nan")), ("vdc", float("inf")), ("bp_vbus_raw", 21),
        ("bp_vbus_valid", 0), ("bp_age_ms", -1), ("bp_age_ms", 300),
        ("bp_vbus_age_ms", 300), ("bp_status", 0x20), ("bp_status", 0x02),
        ("precharge", 1), ("pfc", 1), ("brake", 1), ("bp_ext", 1)):
        check(not bench.isolated_idle(dict(s, **{key: value}), 2026101001))
    check(bench.isolated_idle(dict(s, vdc=2, bp_vbus_raw=20), 2026101001))
    check(not bench.isolated_idle(s, 2026100804))
    counters = {k: 0 for k in (
        "mc_bad_cnt", "mc_bad_integrity", "mc_bad_sequence",
        "mc_uart_error_flags", "mc_last_uart_error_flags", "uno_tx_short_writes")}
    check(bench.transport_clean(counters))
    historical = dict(counters, mc_bad_integrity=1)
    history = bench.reply_history(historical)
    check(not bench.transport_clean(historical))
    check(bench.transport_clean(historical, history))
    check(not bench.transport_clean(dict(historical, mc_bad_integrity=2), history))
    check(not bench.transport_clean(dict(historical, mc_bad_cnt=1), history))
    check(not bench.transport_clean(dict(historical, mc_uart_error_flags=1), history))
    check(bench.transport_clean(dict(historical, mc_bad_cnt=1), history, 1))
    check(not bench.transport_clean(dict(historical, mc_bad_cnt=2), history, 1))
    check(not bench.transport_clean(historical, history, 2))
    check(not bench.transport_clean(counters, {"mc_bad_cnt": 0}))
    try:
        bench.reply_history(dict(historical, mc_bad_integrity=65535))
    except RuntimeError:
        check(True)
    else:
        check(False)
    for key in counters:
        missing = dict(counters)
        del missing[key]
        check(not bench.transport_clean(missing))
        for value in (1, -1, None, False, "0"):
            check(not bench.transport_clean(dict(counters, **{key: value})))
    source = inspect.getsource(bench.main)
    boot = dict(s, mc_fw_build=2026100899, mc_diag_valid=1, bp_fault=1, mc_bad_cnt=1,
                mc_last_bad_reason=12, mc_last_uart_error_flags=2, mc_fault_reason=12,
                mc_uart_error_flags=2, mc_fault_motor_state=0, mc_fault_current_mask=0,
                mc_fault_occurred_mask=0, uno_tx_short_writes=0)
    check(bench.expected_programming_frame_error(boot, 2026101001, 2026100899))
    for key, value in (("pwm", 1), ("vdc", 3), ("mc_fw_build", 2026100801),
                       ("mc_bad_cnt", 2), ("mc_last_bad_reason", 1), ("mc_last_uart_error_flags", 8),
                       ("mc_fault_reason", 1), ("mc_fault_motor_state", 6),
                       ("mc_fault_current_mask", 0x400), ("mc_fault_occurred_mask", 0x400),
                       ("uno_tx_short_writes", 1)):
        check(not bench.expected_programming_frame_error(dict(boot, **{key: value}),
                                                         2026101001, 2026100899))
    owned_stop = dict(s, **counters, mc_fw_build=2026100801, estop=1, mc_diag_valid=1,
                      mc_fault_reason=4, mc_last_bad_reason=0,
                      mc_fault_current_mask=0, mc_fault_occurred_mask=0)
    check(bench.expected_bench_estop(owned_stop, 2026101001, 2026100801))
    for key, value in (("pwm", 1), ("vdc", 3), ("mc_fault_reason", 1), ("mc_last_bad_reason", 1),
                       ("mc_bad_cnt", 1), ("mc_bad_integrity", 1), ("mc_uart_error_flags", 2),
                       ("mc_fault_current_mask", 0x400)):
        check(not bench.expected_bench_estop(dict(owned_stop, **{key: value}),
                                            2026101001, 2026100801))
    check(source.index('"preflash_idle"') < source.index('program(bench_hex'))
    check('fixture_mcsdk_filtered_voltage_limit_v") != 2' in source)
    check('Transport fault preserved; refusing automatic CLEAR' in source)
    check('program(prod_hex, prod_bin, "production")' in source)
    check('"hv_release_approved": False' in source)
    print(json.dumps({"pass": True, "checks": checks, "hardware_commands": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
