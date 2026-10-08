"""No hardware operations: first-trial prechecks only."""
from wifi_motor_first_start import ready, outputs_off
from web_hmi_command_guard_selftest import safe_status


def main():
    s = safe_status(fw_build=2026100707, mc_fw_build=2026100707, mc_diag_valid=1, mc_last_bad_valid=1,
                    hmi_hv_armed=0, hmi_arm_profile='hv', hmi_vbus_hv_calibrated=1,
                    mode='VF', bp_softstart_ready=1, bp_vbus_valid=1,
                    vdc=320.0, bp_vdc=320.0, bp_vbus_raw=3200,
                    bp_temp_age_ms=20, bp_age_ms=20, bp_bad=0)
    assert ready(s) and outputs_off(s)
    count = 1
    assert ready(dict(s, fw_build=2026100708, mc_fw_build=2026100708))
    assert not ready(dict(s, fw_build=2026100708))
    assert not ready(dict(s, mc_fw_build=2026100708))
    count += 3
    assert ready(dict(s, fw_build=2026100709, mc_fw_build=2026100708))
    assert not ready(dict(s, fw_build=2026100709, mc_fw_build=2026100709))
    count += 2
    for k, v in (('pwm',1),('state','VF_RUN'),('mode','FOC'),('bp_fault',5),
                 ('bp_bad_cnt',1),('vdc',0),('vdc',400),('vdc',float('nan')),
                 ('bp_vbus_raw',0),('bp_softstart_ready',0),('bp_age_ms',300),
                 ('bp_temp_age_ms',9999),('bp_temp_fault',1),('bp_temp_c',90),
                 ('hmi_vbus_hv_calibrated',0),('hmi_hv_armed',1),
                 ('mc_fw_build',2026100699),('precharge',1),('mc_diag_valid',0)):
        assert not ready(dict(s, **{k:v})), k
        count += 1
    assert ready(dict(s,bp_fault=5,bp_bad_cnt=2),faults_allowed=True)
    assert not ready(dict(s,pwm=1),faults_allowed=True)
    assert ready(dict(s,enc_ok=0,enc_rpm=0)), 'V/f does not require AS5600'
    print(f'PASS: {count + 3} offline first-trial checks; no commands sent')


if __name__ == '__main__':
    main()
