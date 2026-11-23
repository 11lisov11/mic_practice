"""Read-only Vbus review; retain both saved calibration points and all HV gates."""
import argparse
import json
import math
import re
import statistics
import time
from pathlib import Path

import pwm_filter_hardware_session as bench
from install_passive_break_decoder_fix import ERROR_FIELDS
from ipm_break_wifi_selftest import load_module


def main(folder: Path, meter_vdc: float):
    if not math.isfinite(meter_vdc) or not 0 <= meter_vdc <= 2:
        raise ValueError('This review requires the operator\'s discharged-bus reading, 0..2 V')
    session = bench.Session(folder)
    out = folder / ('vbus_preservation_review_' + str(time.time_ns()))
    out.mkdir()
    archive = folder / 'vbus_recalibration_preparation/original_vbus_calibration.json'
    assert bench.sha(archive) == bench.CAL_SHA
    original = json.loads(archive.read_text())
    server = load_module(bench.PACKAGE / 'production/web_hmi/server.py')
    store = server.VbusCalibrationStore(str(archive))
    assert store.is_valid(), 'Original saved points fail integrity or span verification'
    remote_backup = '/home/arduino/.config/mic-ai/vbus_calibration.json.before_fw1411_fw1410_20261014'
    session.hashes('vbus_preservation_before_' + out.name)
    remote = json.loads(session.remote(f'''from pathlib import Path
import hashlib,json
p=Path('/home/arduino/.config/mic-ai/vbus_calibration.json')
b=Path({remote_backup!r})
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(p)==sha(b)=={bench.CAL_SHA!r}
print(json.dumps(dict(current_sha256=sha(p),backup_sha256=sha(b),record=json.loads(p.read_text()))))
''', 'vbus_preservation_records_' + out.name))
    assert remote['record'] == original
    samples = []
    for _ in range(server.VBUS_CAL_CAPTURE_SAMPLES):
        status = session.idle(False)
        ok, reason = server.vbus_capture_precheck(status, meter_vdc)
        assert ok, reason
        assert all(status.get(field) == 0 for field in ERROR_FIELDS)
        samples.append(status)
        time.sleep(.05)
    identity = server._vbus_calibration_identity(samples[0])
    assert all(server._vbus_calibration_identity(s) == identity for s in samples)
    readings = [float(s['vdc']) for s in samples]
    assert abs(statistics.mean(readings) - meter_vdc) <= server.VBUS_CAL_ZERO_MAX_METER_V
    snapshot = store.snapshot(samples[-1])
    session.hashes('vbus_preservation_after_' + out.name)
    assert bench.sha(archive) == bench.CAL_SHA
    project = bench.PACKAGE / 'production/nucleo'
    vref = float(re.search(r'#define\s+ADC_REFERENCE_VOLTAGE\s+([0-9.]+)',
                          (project / 'Inc/parameters_conversion.h').read_text())[1])
    divider = float(re.search(r'#define\s+VBUS_PARTITIONING_FACTOR\s+([0-9.]+)',
                             (project / 'Inc/power_stage_parameters.h').read_text())[1])
    conversion_factor = int(vref / divider)
    report = dict(
        schema='mic_ai.vbus_preservation_review.v1', pass_=True,
        meter_vdc=meter_vdc, reference_use='Independent discharged-bus check; not a replacement calibration point',
        samples=len(samples), reported_mean_v=statistics.mean(readings),
        reported_std_v=statistics.pstdev(readings), zero_check_pass=True,
        original_calibration_sha256=bench.CAL_SHA, original_calibration_unchanged=True,
        saved_points=original['points'], original_identity=original['identity'],
        current_identity=identity, original_points_integrity_and_span_valid=True,
        current_pair_calibration=snapshot,
        measurement_change=dict(
            change='IIR fractional remainder is retained; prior constant-input lag removed',
            conversion_factor=conversion_factor, prior_max_constant_input_lag_u16=255,
            prior_lag_voltage_bound_v=255 * conversion_factor / 65536,
            qualification='Source and host characterization; not a new powered measurement'),
        calibration_api_calls=0, calibration_writes=0, firmware_writes=0,
        arm_commands=0, start_commands=0, clear_commands=0, hv_release_approved=False,
        policy='Do not repeat calibration for each diagnostic firmware update. Preserve original points. '
               'Review actual measurement changes separately; do not relabel old measurements as current captures.')
    report['pass'] = report.pop('pass_')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (out / 'samples.json').write_text(json.dumps(samples, indent=2) + '\n', encoding='utf-8')
    session.state['vbus_preservation_review'] = str(out)
    session.state['vbus_zero_reference_meter_vdc'] = meter_vdc
    session.state['vbus_zero_reference_recorded_as_calibration'] = False
    session.state['vbus_original_points_preserved'] = True
    session.save()
    print(json.dumps({k: report[k] for k in ('pass', 'samples', 'meter_vdc', 'reported_mean_v',
                     'original_calibration_unchanged', 'current_pair_calibration',
                     'measurement_change', 'calibration_api_calls', 'hv_release_approved')}, indent=2))
    print('Evidence: ' + str(out / 'report.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', type=Path, required=True)
    parser.add_argument('--meter-vdc', type=float, required=True)
    args = parser.parse_args()
    main(args.session.resolve(), args.meter_vdc)
