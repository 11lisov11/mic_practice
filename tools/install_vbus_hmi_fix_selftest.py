"""Offline checks; this module never accesses the live HMI."""
import json
from install_vbus_hmi_fix_remote import precheck
from web_hmi_command_guard_selftest import safe_status


def main():
    base = safe_status(fw_build=2026100612, mc_fw_build=2026100601,
                       bp_mcsdk_telemetry=1, bp_vbus_valid=1, bp_vbus_raw=0,
                       mc_age_ms=20, bp_temp_age_ms=20, hmi_hv_armed=0, bp_fault=5)
    assert precheck(base)[0]
    cases = 1
    for left, right in ((2026100707, 2026100707), (2026100708, 2026100707),
                        (2026100708, 2026100708), (2026100709, 2026100708),
                        (2026100709, 2026100710), (2026100709, 2026100801), (2026100802, 2026100801),
                        (2026100803, 2026100801)):
        assert precheck(dict(base, fw_build=left, mc_fw_build=right))[0]
        cases += 1
    assert not precheck(dict(base, fw_build=2026100707, mc_fw_build=2026100708))[0]
    cases += 1
    for key, value in (('state', 'VF_RUN'), ('pwm', 1), ('hmi_hv_armed', 1),
                       ('estop', 1), ('bp_status', 0x22), ('fw_build', 2026100613),
                       ('mc_fw_build', 2026100602), ('rpc_schema_version', 4),
                       ('mc_capabilities', 3), ('bp_mcsdk_telemetry', 0),
                       ('bp_vbus_valid', 0), ('mc_age_ms', 300),
                       ('bp_vbus_age_ms', 9999), ('bp_temp_age_ms', float('nan')),
                       ('vdc', 322.0), ('bp_vdc', 118.0), ('vdc', -1),
                       ('vdc', float('nan')), ('bp_vbus_raw', 3220),
                       ('bp_temp_valid', 0), ('bp_temp_fault', 1), ('bp_fault', 6),
                       ('precharge', 1), ('pfc', 1), ('brake', 1), ('bp_ext', 1)):
        assert not precheck(dict(base, **{key: value}))[0], key
        cases += 1
    for key in base:
        missing = dict(base)
        missing.pop(key)
        if key in ('state','pwm','hmi_hv_armed','vdc','bp_vdc','bp_fault',
                   'mc_age_ms','bp_temp_valid','bp_temp_fault','bp_temp_age_ms'):
            assert not precheck(missing)[0], key
            cases += 1
    print(json.dumps({'pass': True, 'cases': cases, 'scope': 'offline only'}))


if __name__ == '__main__':
    main()
