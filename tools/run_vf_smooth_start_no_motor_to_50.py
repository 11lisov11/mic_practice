"""Bounded 5..50-Hz inverter switching trial with J3 disconnected.

Uses the existing production pair and staged runner. Import and --self-test
send no hardware commands. The no-motor state is an operator confirmation,
not something this script can detect electrically.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

import prepare_vf_smooth_start as package
import run_vf_smooth_start_to_50 as existing

runner = existing.tested.runner
runner.PROFILE = 'vf-smooth-start-no-motor-5-to-50'
ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'artifacts/live_bench_20261024/no_motor_to_50_prepare_r1/idle_usb/final_status.json'


def selftest(out):
    """Exercise real preflight guards using explicitly synthetic HV statuses."""
    s = json.loads(BASELINE.read_text(encoding='utf-8'))
    s.update(vdc=320.0, bp_vdc=320.0, bp_vbus_raw=3200,
             bp_softstart_ready=1, mc_fault=0, bp_fault=0,
             mc_fault_current_mask=0, mc_fault_occurred_mask=0,
             mc_fault_reason=0)
    assert runner.ready(s) and runner.capture_free(s)
    checks = 1
    for key, value in (
        ('vdc', 1), ('bp_vdc', 351), ('mc_age_ms', 300),
        ('bp_softstart_ready', 0), ('bp_temp_c', 80), ('pwm', 1),
        ('hmi_hv_armed', 1), ('estop', 1), ('mc_transport_fault', 5),
        ('mc_bad_integrity', 1), ('mc_bad_sequence', 1),
        ('mc_uart_error_flags', 4), ('uno_rx_dropped', 1),
        ('mc_fw_build', 2026102104), ('mc_fault_current_mask', 1024),
        ('mc_uart_reject_bad_pages', 1),
    ):
        bad = dict(s, **{key: value})
        assert not runner.ready(bad), key
        checks += 1
    for key, value in (
        ('level', 'LOW'), ('config_ok', False),
        ('break_irq_enabled', False), ('capture_running', False),
        ('first_record_ready', True),
    ):
        bad = copy.deepcopy(s)
        bad['mc_sd_live'][key] = value
        assert not runner.ready(bad), key
        checks += 1
    occupied = copy.deepcopy(s)
    occupied['mc_break_snapshots'][0]['captured'] = True
    assert not runner.capture_free(occupied)
    checks += 1
    uv = dict(s, mc_fault=5, bp_fault=5, mc_fault_reason=8,
              mc_fault_current_mask=0, mc_fault_occurred_mask=4)
    assert existing.tested.startup_ack_allowed(uv)
    for key, value in (('mc_fault_occurred_mask', 1024),
                       ('mc_transport_fault', 5), ('vdc', 1)):
        assert not existing.tested.startup_ack_allowed(dict(uv, **{key: value}))
        checks += 1
    assert [hz for hz, _ in runner.PLAN] == list(range(5, 51, 5))
    assert runner.MAX_RUN_S == 100 and runner.HOLD_S == 2
    checks += 2
    out.mkdir(parents=True, exist_ok=False)
    report = dict(passed=True, checks=checks, synthetic_powered_fixtures=True,
                  start_commands=0, arm_commands=0, clear_commands=0,
                  flash_commands=0, hardware_commands=0,
                  targets_hz=[hz for hz, _ in runner.PLAN],
                  host_deadline_s=runner.MAX_RUN_S, operator_watchdog_s=3,
                  physical_no_motor_run_performed=False)
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--confirm-motor-disconnected', action='store_true')
    parser.add_argument('--confirm-powered-ready', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        return selftest(args.outdir.resolve())
    if not (args.confirm_motor_disconnected and args.confirm_powered_ready):
        parser.error('Both J3-disconnected and autonomous powered-ready confirmations required')
    original_argv = sys.argv
    sys.argv = [original_argv[0], '--outdir', str(args.outdir), '--confirm-powered-ready']
    try:
        result = runner.main()
    finally:
        sys.argv = original_argv
    report_path = args.outdir.resolve() / 'report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report.update(motor_connected=False,
                  motor_disconnection_source='operator confirmation, not electrically detected',
                  phase_current_measured=False,
                  physical_pwm_waveform_measured=False,
                  diagnosis_limitation='A successful unloaded inverter trial does not prove motor failure or inverter health under load.')
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    raise SystemExit(main())
