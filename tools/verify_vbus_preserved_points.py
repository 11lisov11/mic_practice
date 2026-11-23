"""Verify a measured working bus over GET-only Wi-Fi; never rewrite calibration."""
import argparse
import json
import math
import statistics
import time
from pathlib import Path

import pwm_filter_hardware_session as bench
from collect_wifi_telemetry import get_status
from install_passive_break_decoder_fix import ERROR_FIELDS
from ipm_break_wifi_selftest import load_module

PAIR = (2026101411, 2026101410)


def reasons(status):
    errors = []
    def need(condition, label):
        if not condition:
            errors.append(label)
    need((status.get('fw_build'), status.get('mc_fw_build')) == PAIR, 'firmware pair')
    need(status.get('state') == 'SAFE' and status.get('pwm') == 0
         and status.get('hmi_hv_armed') == 0 and status.get('estop') == 0, 'disarmed SAFE')
    need(type(status.get('bp_status')) is int and not (status['bp_status'] & 0x22), 'controller outputs off')
    need(all(status.get(k) == 0 for k in ('precharge', 'pfc', 'brake', 'bp_ext')), 'external outputs off')
    need(status.get('bp_transport_fault') == 0
         and all(status.get(k) == 0 for k in ERROR_FIELDS), 'transport errors')
    need(status.get('rpc_schema_version') == 3 and status.get('mc_capabilities') == 1
         and status.get('bp_mcsdk_telemetry') == 1, 'measurement schema')
    need(status.get('bp_vbus_valid') == 1 and status.get('bp_temp_valid') == 1
         and status.get('bp_temp_fault') == 0, 'sensor validity')
    for key in ('bp_age_ms', 'bp_vbus_age_ms', 'bp_temp_age_ms'):
        value = status.get(key)
        need(type(value) in (int, float) and math.isfinite(value) and 0 <= value < 300, key)
    vdc, raw, temp = status.get('vdc'), status.get('bp_vbus_raw'), status.get('bp_temp_c')
    need(type(vdc) in (int, float) and math.isfinite(vdc) and 250 <= vdc <= 360, 'working bus range')
    need(type(raw) is int and type(vdc) in (int, float) and abs(raw * .1 - vdc) <= 1, 'Vbus word agreement')
    need(type(temp) in (int, float) and math.isfinite(temp) and -20 <= temp <= 80, 'temperature')
    # Reading with a retained zero-bus UV record is permitted; ARM/CLEAR are not sent.
    need(status.get('bp_fault') in (0, 5) and status.get('mc_fault_current_mask') == 0
         and status.get('mc_fault_occurred_mask') in (0, 4), 'only retained undervoltage; no current fault')
    return errors


def capture(session, meter, out):
    if not math.isfinite(meter) or not 250 <= meter <= 360:
        raise ValueError('Supply a NEW independent working-bus reading, 250..360 V; do not reuse the old 322.7 V')
    assert bench.PROD == PAIR
    out.mkdir(parents=True, exist_ok=False)
    server = load_module(bench.PACKAGE / 'production/web_hmi/server.py')
    rows = []
    report = dict(schema='mic_ai.vbus_preserved_points_verification.v1', pass_=False,
                  meter_vdc=meter, transport='direct_wifi_http_get_only',
                  calibration_writes=0, arm_commands=0, start_commands=0, clear_commands=0,
                  firmware_writes=0, hv_release_approved=False,
                  scope='Independent working-bus comparison; does not unlock calibration or motor START')
    try:
        session.hashes('vbus_readonly_before_' + out.name)
        for _ in range(server.VBUS_CAL_CAPTURE_SAMPLES):
            status = get_status(session.opener, 'http://192.168.1.138:8080')
            rows.append(status)
            rejected = reasons(status)
            if rejected:
                raise ValueError('Working-bus observation rejected: ' + ', '.join(rejected))
            time.sleep(.05)
        values = [s['vdc'] for s in rows]
        mean, std = statistics.mean(values), statistics.pstdev(values)
        allowed_error = max(server.VBUS_CAL_HV_MAX_ERROR_FLOOR_V,
                            meter * server.VBUS_CAL_HV_MAX_ERROR_PERCENT / 100)
        allowed_std = max(server.VBUS_CAL_HV_MAX_STD_FLOOR_V,
                          meter * server.VBUS_CAL_HV_MAX_STD_PERCENT / 100)
        report.update(samples=len(rows), mean_v=mean, std_v=std, error_v=mean-meter,
                      allowed_error_v=allowed_error, allowed_std_v=allowed_std,
                      first=rows[0], last=rows[-1])
        session.hashes('vbus_readonly_after_' + out.name)
        report['original_calibration_unchanged'] = True
        report['pass_'] = abs(mean-meter) <= allowed_error and std <= allowed_std
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        report['pass'] = report.pop('pass_')
        (out / 'samples.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('first', 'last')}, indent=2))
    return report['pass']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--meter-vdc', type=float, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    session = bench.Session(args.session.resolve())
    raise SystemExit(0 if capture(session, args.meter_vdc, args.outdir.resolve()) else 1)
