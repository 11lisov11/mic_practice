"""Fail-closed installer safety predicates; never contact boards."""
import json
from install_uart_v3_pair import initial_idle, new_idle
from web_hmi_command_guard_selftest import safe_status


def main():
    tests = 0

    def reject(callback):
        nonlocal tests
        try:
            callback()
        except (RuntimeError, ValueError, TypeError, KeyError):
            tests += 1
            return
        raise AssertionError("unsafe installer state accepted")

    old = safe_status(fw_build=2026101002, mc_fw_build=2026100801,
                      state="SAFE", pwm=0, hmi_hv_armed=0, bp_status=9, bp_fault=5,
                      bp_mcsdk_telemetry=1, bp_vbus_valid=1, bp_vbus_raw=10,
                      vdc=1.0, bp_vdc=1.0, mc_age_ms=25,
                      bp_vbus_age_ms=25, bp_temp_age_ms=25,
                      mc_bad_cnt=0, mc_bad_integrity=0, mc_bad_sequence=0,
                      mc_uart_error_flags=0, mc_last_uart_error_flags=0,
                      uno_tx_short_writes=0)
    initial_idle(old); tests += 1
    for field, value in (("vdc",2.1),("bp_vdc",300),("pwm",1),("state","VF_RUN"),
                         ("hmi_hv_armed",1),("estop",1),("mc_bad_cnt",1),
                         ("mc_uart_error_flags",4),("mc_bad_integrity",1),
                         ("fw_build",2026101004),("mc_fw_build",2026101003)):
        reject(lambda field=field,value=value:initial_idle(dict(old,**{field:value})))
    new = dict(old, fw_build=2026101004, mc_fw_build=2026101003,
               mc_diag_valid=1, mc_fault_reason=8, mc_last_bad_reason=0,
               mc_fault_motor_state=10, mc_fault_current_mask=4, mc_fault_occurred_mask=4,
               bp_ne_accepted=0, bp_ne_observed=0, bp_ne_flags=0, bp_transport_fault=0)
    new_idle(new); new_idle(new,True); tests += 2
    for field,value in (("vdc",2.01),("vdc",float("nan")),("bp_vdc",float("inf")),
                        ("bp_vbus_raw",21),("mc_age_ms",300),("bp_temp_age_ms",-1),
                        ("mc_fault_current_mask",0x400),("mc_fault_occurred_mask",0x404),
                        ("bp_temp_c",80),("bp_temp_c",float("nan")),("estop",1),
                        ("pwm",1),("bp_status",0x20),("state","VF_RUN"),("hmi_hv_armed",1),
                        ("rpc_schema_version",4),("mc_capabilities",3),("precharge",1),
                        ("bp_ext",1),("mc_diag_valid",0),("mc_bad_integrity",1),
                        ("mc_bad_sequence",1),("uno_tx_short_writes",1),("bp_ne_flags",None),
                        ("fw_build",2026101002),("mc_fw_build",2026100899)):
        reject(lambda field=field,value=value:new_idle(dict(new,**{field:value}),True))
    for field in ("bp_ne_accepted","bp_ne_observed","bp_ne_flags","bp_transport_fault"):
        missing=dict(new); missing.pop(field)
        reject(lambda missing=missing:new_idle(missing))
    for field,value in (("mc_bad_cnt",1),("bp_transport_fault",6),("mc_last_bad_reason",1)):
        reject(lambda field=field,value=value:new_idle(dict(new,**{field:value})))
    cutover=dict(new,mc_bad_cnt=20,mc_last_bad_reason=13,bp_transport_fault=6)
    new_idle(cutover,True); tests+=1
    for field,value in (("mc_fault_reason",12),("mc_last_bad_reason",12),
                        ("mc_uart_error_flags",4),("mc_last_uart_error_flags",2),
                        ("mc_fault_motor_state",6),("mc_fault_current_mask",0x400)):
        reject(lambda field=field,value=value:new_idle(dict(cutover,**{field:value}),True))
    print(json.dumps({"pass":True,"cases":tests,"hardware_commands":0}))


if __name__=="__main__":
    main()
