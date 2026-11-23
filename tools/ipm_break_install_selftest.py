"""Fail-closed tests of the new pair's low-voltage installer gate, no hardware."""
import json
from install_ipm_break_wifi_pair import idle_safe, OLD_PAIR, NEW_PAIR, UNO_ID
from web_hmi_command_guard_selftest import safe_status


def main():
    cases = 0
    base = safe_status(fw_build=OLD_PAIR[0], mc_fw_build=OLD_PAIR[1], bp_transport_fault=0,
                       bp_bad_integrity=0, bp_bad_sequence=0, bp_clear_pending=0,
                       bp_mcsdk_telemetry=1, bp_vbus_valid=1, bp_vbus_raw=0,
                       mc_age_ms=25, hmi_hv_armed=0, bp_bad=0)
    for pair in (OLD_PAIR, (UNO_ID, OLD_PAIR[1]), NEW_PAIR):
        status = dict(base, fw_build=pair[0], mc_fw_build=pair[1])
        assert idle_safe(status); cases += 1
    maintenance = dict(base, bp_fault=5, mc_diag_valid=1, mc_fault_reason=8,
                       mc_fault_current_mask=4, mc_fault_occurred_mask=0x404)
    assert idle_safe(maintenance); cases += 1
    assert idle_safe(dict(maintenance, mc_fault_occurred_mask=4)); cases += 1
    for field, bad in (("mc_fault_reason", 11), ("mc_diag_valid", 0),
                       ("mc_fault_current_mask", 0x400), ("mc_fault_current_mask", 2),
                       ("mc_fault_occurred_mask", 0x440), ("vdc", 3), ("pwm", 1)):
        assert not idle_safe(dict(maintenance, **{field: bad})); cases += 1
    flash_pause = dict(base, fw_build=UNO_ID, bp_fault=2, bp_status=25,
                       bp_transport_fault=7, bp_bad_cnt=1, mc_last_bad_reason=13,
                       mc_last_uart_error_flags=0)
    assert idle_safe(flash_pause); cases += 1
    one_boot_reject = dict(flash_pause, bp_bad=1, bp_bad_integrity=1)
    assert not idle_safe(one_boot_reject); cases += 1
    assert idle_safe(one_boot_reject, maintenance_boot_reject=True); cases += 1
    for count in (5, 65535):
        historical = dict(flash_pause, bp_bad=count, bp_bad_integrity=count)
        assert not idle_safe(historical) and idle_safe(historical, maintenance_boot_reject=True); cases += 1
    for field, bad in (("bp_bad", -1), ("bp_bad", 65536), ("bp_bad_integrity", 2), ("bp_bad_sequence", 1), ("vdc", 3), ("pwm", 1)):
        assert not idle_safe(dict(one_boot_reject, **{field: bad}), maintenance_boot_reject=True); cases += 1
    for field, bad in (("fw_build", OLD_PAIR[0]), ("mc_fw_build", NEW_PAIR[1]),
                       ("mc_last_bad_reason", 12), ("mc_last_uart_error_flags", 4),
                       ("bp_bad_integrity", 1), ("bp_bad_sequence", 1), ("bp_bad_cnt", 2),
                       ("bp_status", 0x3B), ("vdc", 2.1)):
        assert not idle_safe(dict(flash_pause, **{field: bad})); cases += 1
    for field, bad in (("state", "RUN"), ("pwm", 1), ("hmi_hv_armed", 1), ("estop", 1),
        ("fw_build", 0), ("mc_fw_build", 0), ("bp_status", 0x21), ("rpc_schema_version", 4),
        ("mc_capabilities", 3), ("bp_temp_valid", 0), ("bp_temp_fault", 1), ("bp_vdc", 2.1),
        ("vdc", float("nan")), ("vdc", float("inf")), ("bp_vbus_raw", 21), ("bp_vbus_raw", 0.5),
        ("mc_age_ms", 300), ("bp_temp_age_ms", -1), ("bp_vbus_age_ms", float("inf")),
        ("bp_fault", 5), ("bp_bad", 1), ("bp_bad_cnt", 1), ("bp_bad_integrity", 1),
        ("bp_bad_sequence", 1), ("bp_transport_fault", 1), ("bp_clear_pending", 1),
        ("precharge", 1), ("pfc", 1), ("brake", 1), ("bp_ext", 1)):
        assert not idle_safe(dict(base, **{field: bad})), field; cases += 1
    for field in ("vdc", "bp_status", "bp_transport_fault", "mc_age_ms", "mc_fw_build"):
        status = dict(base); del status[field]
        assert not idle_safe(status); cases += 1
    print(json.dumps(dict(pass_=True, cases=cases, hardware_commands=0)))


if __name__ == "__main__":
    main()
