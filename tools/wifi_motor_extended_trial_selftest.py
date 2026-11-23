"""Offline extended-trial gates; no controller commands."""
import json

from web_hmi_command_guard_selftest import safe_status
from wifi_motor_extended_trial import owned_previous_stop, running_healthy


def main():
    checks = 0

    def check(v):
        nonlocal checks
        assert v
        checks += 1

    s = safe_status(fw_build=2026101002, mc_fw_build=2026100801,
        hmi_hv_armed=0, hmi_arm_profile='hv', hmi_vbus_hv_calibrated=1,
        hmi_bounded_start_request_supported=1, mode='VF', bp_softstart_ready=1,
        bp_vbus_valid=1, vdc=325.0, bp_vdc=325.0, bp_vbus_raw=3250,
        bp_age_ms=20, bp_bad=0, mc_diag_valid=1, mc_last_bad_valid=1,
        estop=1, bp_fault=1, mc_fault_reason=4, mc_fault_sequence=42,
        mc_fault_motor_state=6, mc_fault_current_mask=0, mc_fault_occurred_mask=0,
        mc_bad_cnt=0, mc_bad_integrity=0, mc_bad_sequence=0,
        mc_last_bad_reason=0, mc_uart_error_flags=0, mc_last_uart_error_flags=0,
        uno_tx_short_writes=0)
    previous = {'pass': True, 'final_stop': {'ok': True}, 'final_status': dict(s)}
    check(owned_previous_stop(s, previous))
    for k, v in (('mc_fault_sequence', 43), ('mc_fault_reason', 1), ('mc_bad_cnt', 1),
                 ('mc_fault_occurred_mask', 0x400), ('pwm', 1), ('vdc', 400),
                 ('hmi_hv_armed', 1), ('mc_bad_integrity', 1), ('estop', 0)):
        check(not owned_previous_stop(dict(s, **{k: v}), previous))
    check(not owned_previous_stop(s, dict(previous, **{'pass': False})))
    active = dict(s, state='VF_RUN', pwm=1, bp_status=0x63, estop=0,
                  bp_fault=0, hmi_hv_armed=1, freq=5.0, freq_cmd=10)
    check(running_healthy(active))
    for k, v in (('freq', 11), ('freq', float('nan')), ('freq_cmd', 20),
                 ('mc_bad_cnt', 1), ('mc_bad_sequence', 1), ('bp_fault', 1),
                 ('bp_temp_c', 80), ('bp_age_ms', 300), ('vdc', 400),
                 ('hmi_hv_armed', 0), ('pwm', 0), ('precharge', 1)):
        check(not running_healthy(dict(active, **{k: v})))
    print(json.dumps({'pass': True, 'checks': checks, 'hardware_commands': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
