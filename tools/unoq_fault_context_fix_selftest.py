"""Test extended fault history using the exact candidate Linux HMI."""
import argparse
import json
import tempfile
from pathlib import Path

from prepare_unoq_fault_context_fix import BASE, FIELDS, patched
from ipm_break_wifi_selftest import load_module


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    a = p.parse_args()
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    checks = 0

    def check(ok):
        nonlocal checks
        checks += 1
        assert ok

    with tempfile.TemporaryDirectory() as d:
        file = Path(d) / 'server.py'
        old = load_module(BASE)
        file.write_text(patched(BASE.read_text()))
        new = load_module(file)
        check(set(new.MotorFaultRecorder.FIELDS) - set(old.MotorFaultRecorder.FIELDS) == set(FIELDS))
        check(set(old.MotorFaultRecorder.FIELDS) <= set(new.MotorFaultRecorder.FIELDS))
        check(new.MotorFaultRecorder.KEY_FIELDS == old.MotorFaultRecorder.KEY_FIELDS)
        # The entire actuator/gating part of the module stays byte-identical.
        check(patched(BASE.read_text()).split('def supported_modes_from_caps', 1)[1]
              == BASE.read_text().split('def supported_modes_from_caps', 1)[1])
        healthy = dict(state='SAFE', pwm=0, mc_fault=0, bp_fault=0, mc_diag_valid=1,
                       mc_fault_reason=0, mc_bad_cnt=0, mc_fw_build=2026101102,
                       uno_tx_all_max_gap_us=51000, uno_tx_last_gap_us=50000,
                       uno_tx_gaps_over_watchdog=0, uno_rx_dropped=0, uno_rx_hw_errors=0,
                       uno_rx_hw_flags=0, mc_transport_fault=0, uno_rx_rejected_hex='-',
                       enc_errors=0)
        rec = new.MotorFaultRecorder()
        check(not rec.observe(healthy, now=0))
        stalled = dict(healthy, uno_tx_last_gap_us=290000)
        check(not rec.observe(stalled, now=.2))
        fault = dict(stalled, bp_fault=5, mc_fault=5, mc_fault_reason=13,
                     mc_bad_cnt=1, mc_transport_fault=7, uno_tx_all_max_gap_us=350000,
                     uno_tx_gaps_over_watchdog=1, uno_rx_rejected_hex='ab00',
                     control_token='do-not-log-me')
        event = json.loads(rec.observe(fault, now=.4)[0].split(' ', 1)[1])
        check(event['before'][-1]['uno_tx_last_gap_us'] == 290000)
        check(event['at']['uno_tx_gaps_over_watchdog'] == 1)
        check(event['at']['mc_transport_fault'] == 7)
        check(event['at']['uno_rx_rejected_hex'] == 'ab00')
        check('do-not-log-me' not in json.dumps(event))
        check(event['physical_source_identified'] is False)
        check(event['time_basis'] == 'Linux observation, not exact MCU interrupt timestamp')
        lines = rec.observe(dict(fault, uno_rx_hw_errors=1), now=.41)
        check(bool(lines) and json.loads(lines[0].split(' ', 1)[1])['at']['uno_rx_hw_errors'] == 1)
        check(not rec.observe(dict(fault, uno_rx_hw_errors=1), now=.42))
        compact = rec.compact(dict(fault, uno_rpc_max_us=float('nan')), 1)
        check(compact['uno_rpc_max_us'] is None)
        legacy = rec.compact({'state': 'SAFE'}, 2)
        check(all(legacy[k] is None for k in FIELDS))
        for i in range(500):
            rec.observe(healthy, now=10 + i * .2)
        check(len(rec._history) == 64)
    report = dict(pass_=True, checks=checks, hardware_commands=0,
                  control_guards_changed=False, mcu_firmware_changed=False)
    report['pass'] = report.pop('pass_')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
