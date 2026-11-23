"""One bounded scalar trial to diagnose AS5600; sensor is observation only.

Transport mode must have been selected and checked with outputs OFF before
the operator enables J1. No CLEAR, reset, flash, repeated START or automatic
mode change. Existing drive, SD, current, temperature and UART checks remain.
"""
import argparse
import json
from pathlib import Path
import sys

import run_current_shunt_5hz as trial
from current_zero_quality import ready as zero_ready

MODES = {'HW100': 0, 'SW100': 1, 'SW25': 2, 'LEGACY': 3}


def diagnostic_state(s, mode):
    return (s.get('enc_source') == 'uno_q_i2c2'
            and s.get('enc_diag_mode') == mode and s.get('enc_diag_epoch', 0) > 0
            and s.get('enc_init_error') == 0
            and (mode != 3 or s.get('enc_diag_thread_priority') == 14))


def sensor_idle_ready(s, mode):
    # Magnetic quality is intentionally independent of bus validity.
    return (diagnostic_state(s, mode) and s.get('enc_bus_ok') == 1
            and s.get('enc_io_error') == 0 and 0 <= s.get('enc_age_ms', 999999) < 100)


def summarize(report, mode):
    active = [r['status'] for r in report.get('samples', []) if r['status'].get('pwm') == 1]
    baseline = report.get('before', {})
    fields = ('enc_reads', 'enc_errors', 'enc_diag_cause', 'enc_diag_stage',
              'enc_diag_us', 'enc_diag_wait_us', 'enc_diag_first_ms',
              'enc_diag_first_stage', 'enc_diag_first_cause', 'enc_diag_first_us',
              'enc_diag_last_ms', 'enc_diag_last_mode', 'enc_diag_last_stage',
              'enc_diag_last_cause', 'enc_diag_last_us', 'enc_age_ms', 'enc_status')
    fields += ('enc_diag_thread_priority', 'enc_diag_cfg_expected', 'enc_diag_cfg_before',
               'enc_diag_cfg_after', 'enc_diag_cfg_match', 'enc_diag_last_cfg_before',
               'enc_diag_last_cfg_after', 'enc_diag_last_tx_byte',
               'enc_diag_last_tx_echo', 'enc_diag_last_tx_bits')
    return dict(mode=mode, active_samples=len(active),
        sensor_used_for_motor_feedback=False, magnetic_quality_required_for_trial=False,
        drive_protection_checks_unchanged=True,
        errors_since_preflight=(max(s['enc_errors'] for s in active)-baseline['enc_errors']) if active else None,
        reads_since_preflight=(max(s['enc_reads'] for s in active)-baseline['enc_reads']) if active else None,
        fresh_bus_ok_snapshots=sum(s.get('enc_bus_ok') == 1 for s in active),
        valid_angle_snapshots=sum(s.get('enc_ok') == 1 for s in active),
        observed_causes=sorted({s.get('enc_diag_cause') for s in active}),
        observed_stages=sorted({s.get('enc_diag_stage') for s in active}),
        maximum_transaction_us=max((s.get('enc_diag_us', 0) for s in active), default=0),
        samples=[{k:s.get(k) for k in fields} for s in active],
        physical_cause_proven=False,
        limitations=['Mode names are nominal clock timings; actual GPIO timings include overhead/preemption',
                     'A successful slower software transport does not alone identify the physical source',
                     'Native generic EIO is not classified as NACK without wire-level evidence'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=MODES, required=True)
    p.add_argument('--uno-build', type=int, choices=(2026102513,2026102515), default=2026102513)
    p.add_argument('--confirm-powered-ready', action='store_true')
    p.add_argument('--outdir', type=Path, required=True)
    args = p.parse_args()
    if not args.confirm_powered_ready:
        p.error('Fresh operator confirmation of autonomous powered bench required')
    if args.mode == 'LEGACY' and args.uno_build != 2026102515:
        p.error('LEGACY requires verified Uno2026102515')
    mode = MODES[args.mode]
    original_ready, original_active = trial.ready, trial.checks.active
    trial.checks.PAIR = (args.uno_build, 2026102510)
    trial.zero_ok = zero_ready
    trial.startup_uv_only = lambda _: False  # no automatic ACK
    trial.ready = lambda s: original_ready(s) and sensor_idle_ready(s, mode)
    # Transfer errors are the quantity being measured, not a motor trip. Mode
    # changes or setup failures abort. All original drive checks still apply.
    trial.checks.active = lambda s: original_active(s) and diagnostic_state(s, mode)
    saved_argv = sys.argv
    sys.argv = [saved_argv[0], '--confirm-powered-ready', '--outdir', str(args.outdir)]
    try:
        code = trial.main()
    finally:
        sys.argv = saved_argv
    path = args.outdir / 'report.json'
    if path.exists():
        r = json.loads(path.read_text(encoding='utf-8'))
        summary = summarize(r, args.mode)
        r['i2c_diagnostic'] = summary
        path.write_text(json.dumps(r, indent=2) + '\n', encoding='utf-8')
        (args.outdir / 'i2c_result.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps({k:v for k,v in summary.items() if k != 'samples'}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
