"""Offline state/voltage checks and no-restart-on-missed-contact regression."""
from copy import deepcopy
from run_ipm_physical_sd_bench import safe_status, restart_probe_allowed, PRODUCTION, UNO


def main():
    s = dict(state='SAFE', pwm=0, hmi_hv_armed=0, estop=0, fw_build=UNO,
             mc_fw_build=PRODUCTION, bp_vbus_valid=1, bp_vbus_age_ms=9,
             bp_age_ms=9, vdc=9., bp_vbus_raw=90, bp_status=9,
             precharge=0, pfc=0, brake=0, bp_ext=0)
    assert safe_status(s, PRODUCTION)
    assert safe_status(dict(s, hmi_hv_armed=1), PRODUCTION, expected_armed=1)
    assert not safe_status(s, PRODUCTION, expected_armed=1)
    for k, value in [('vdc', 10.01), ('vdc', float('nan')), ('vdc', -1),
                     ('bp_vbus_raw', 101), ('bp_vbus_age_ms', 300), ('bp_age_ms', -1),
                     ('pwm', 1), ('pwm', False), ('hmi_hv_armed', 1), ('estop', 1),
                     ('bp_status', 0x20), ('mc_fw_build', 2026100707), ('bp_ext', 8)]:
        bad = dict(s, **{k: value})
        assert not safe_status(bad, PRODUCTION), (k, value)
    for k in list(s):
        bad = deepcopy(s)
        del bad[k]
        assert not safe_status(bad, PRODUCTION), k
    fault = dict(s, mc_diag_valid=1, mc_fault_occurred_mask=0x400, bp_fault=5)
    assert restart_probe_allowed(True, fault)
    assert not restart_probe_allowed(False, fault)
    assert not restart_probe_allowed(True, dict(fault, bp_fault=0))
    assert not restart_probe_allowed(True, dict(fault, mc_fault_occurred_mask=0))
    assert not restart_probe_allowed(True, dict(fault, hmi_hv_armed=1))
    assert not restart_probe_allowed(True, dict(fault, pwm=1))
    assert not restart_probe_allowed(True, dict(fault, mc_diag_valid=0))
    print('PASS low-voltage guards, missing/invalid fields and no repeat START after a missed contact')


if __name__ == '__main__':
    main()
