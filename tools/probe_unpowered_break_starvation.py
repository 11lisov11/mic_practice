"""Bounded, zero-bus BKIN polarity stimulus; no START, flash, halt or reset."""
import argparse
import getpass
import hashlib
import json
from pathlib import Path
import subprocess
import time

from run_wifi_nucleo_pwm_bench import WifiHmi
from wifi_stop_tail_probe import parse_registers

CLI = 'C:/Program Files/STMicroelectronics/STM32Cube/STM32CubeProgrammer/bin/STM32_Programmer_CLI.exe'
SERIAL = '003A002C3335510933383531'
GPIOA = 0x48000000
TIM1 = 0x40012C00
AF1 = TIM1 + 0x60
BDTR = TIM1 + 0x44
DHCSR = 0xE000EDF0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-unpowered-j4-off', action='store_true', required=True)
    p.add_argument('--outdir', type=Path, required=True)
    p.add_argument('--uno-build', type=int, default=2026100706)
    p.add_argument('--nucleo-build', type=int, default=2026100705)
    p.add_argument('--image', type=Path)
    p.add_argument('--clear-after', action='store_true')
    p.add_argument('--hold-sec', type=float, default=.35)
    a = p.parse_args()
    if not .05 <= a.hold_sec <= 2:
        p.error('hold-sec outside .05..2 seconds')
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    token = getpass.getpass('CLEAR credential (not echoed): ').strip() if a.clear_after else ''
    if a.clear_after and len(token) < 16:
        raise RuntimeError('Missing CLEAR credential')
    commands = []
    h = WifiHmi('http://192.168.1.138:8080', token, commands, via_wsl=True)
    report = {'motor_commands_sent': [], 'firmware_modified': False, 'pass': False,
              'scope': 'zero-bus, outputs already off; synthetic sustained BKIN level, not physical IPM qualification'}
    original = None
    changed = False

    def cli(name, args):
        r = subprocess.run([CLI, '-c', 'port=SWD', 'mode=HOTPLUG', 'sn='+SERIAL, *args],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
        (out/(name+'.log')).write_text(r.stdout+r.stderr, encoding='utf-8')
        if r.returncode:
            raise RuntimeError('ST-Link operation failed: '+name)
        return parse_registers(r.stdout)

    def regs(name):
        return cli(name, ['-r32', hex(TIM1), '104', '-r32', hex(GPIOA), '40',
                          '-r32', hex(DHCSR), '4', '-r32', '0x200003b0', '8'])

    def safe(s):
        return (s.get('fw_build') == a.uno_build and s.get('mc_fw_build') == a.nucleo_build
                and s.get('pwm') == 0 and s.get('state') == 'SAFE'
                and s.get('hmi_hv_armed') == 0 and 0 <= float(s.get('vdc', 999)) <= 2
                and float(s.get('mc_age_ms', 999)) < 300)

    try:
        before = h.status()
        report['before'] = before
        if not safe(before):
            raise RuntimeError('Expected current disarmed zero-bus working pair')
        root = Path(__file__).resolve().parents[1]
        expected = a.image.resolve() if a.image else root/'artifacts/current_pwm_20261007/capture_r3/production_readback.bin'
        cli('readback', ['-u', '0x08000000', str(expected.stat().st_size), str(out/'readback.bin')])
        actual = hashlib.sha256((out/'readback.bin').read_bytes()).hexdigest()
        if actual != hashlib.sha256(expected.read_bytes()).hexdigest():
            raise RuntimeError('Nucleo image does not match audited address layout')
        report['image_sha256'] = actual
        b = regs('before_registers')
        original = b[AF1]
        if (b[BDTR] & (1<<15) or not b[BDTR] & (1<<12)
                or b[BDTR] & (1<<14) or not original & (1<<9)
                or not original & 1 or not b[GPIOA+0x10] & (1<<6)
                or b[DHCSR] & (1<<17)):
            raise RuntimeError('Expected MOE off, BKE on, AOE off, active-low source, PA6 HIGH and running core')
        # Mark restoration required before the write; ambiguous outcomes also restore.
        changed = True
        cli('assert_break', ['-w32', hex(AF1), hex(original & ~(1<<9))])
        time.sleep(a.hold_sec)
        during = regs('during_registers')
        report['during'] = {hex(k):hex(v) for k,v in during.items()}
        report['break_flag_observed'] = bool(during[TIM1+0x10] & (1<<7))
        report['core_not_halted'] = not bool(during[DHCSR] & (1<<17))
        report['MOE_stayed_off'] = not bool(during[BDTR] & (1<<15))
        report['break_irq_masked'] = not bool(during[TIM1+0x0C] & (1<<7))
        report['requested_hold_s'] = a.hold_sec
        cli('release_break', ['-w32', hex(AF1), hex(original)])
        changed = False
        time.sleep(.5)
        after = h.status()
        report['after'] = after
        report['new_errors'] = int(after['mc_bad_cnt']) - int(before['mc_bad_cnt'])
        report['rx_overflow_reproduced'] = (report['new_errors'] > 0
                                           and after.get('mc_last_bad_reason') == 14)
        report['pass'] = safe(after) and report['MOE_stayed_off'] and report['core_not_halted']
        if a.nucleo_build == 2026100707:
            report['pass'] = report['pass'] and report['break_irq_masked'] and report['new_errors'] == 0
        if a.clear_after:
            if not safe(after):
                raise RuntimeError('Cannot CLEAR outside zero-bus SAFE state')
            h.command('CLEAR')
            time.sleep(.5)
            clean = regs('clear_rearm_registers')
            report['clean_CLEAR_BIE_rearmed'] = bool(clean[TIM1+0x0C] & (1<<7))
            report['clean_CLEAR_break_flags_clear'] = not bool(clean[TIM1+0x10] & ((1<<7)|(1<<8)))
            report['clean_CLEAR_MOE_off'] = not bool(clean[BDTR] & (1<<15))
            report['after_CLEAR'] = h.status()
            report['pass'] = report['pass'] and safe(report['after_CLEAR']) and all(report[k] for k in
                ('clean_CLEAR_BIE_rearmed','clean_CLEAR_break_flags_clear','clean_CLEAR_MOE_off'))
    except Exception as exc:
        report['error'] = str(exc)
    finally:
        if changed and original is not None:
            try:
                cli('emergency_restore', ['-w32', hex(AF1), hex(original)])
            except Exception as exc:
                report['restore_error'] = str(exc)
        if original is not None:
            try:
                restored = regs('restored_registers')
                report['restored_exact_AF1'] = restored[AF1] == original
                report['restored_MOE_off'] = not bool(restored[BDTR] & (1<<15))
                report['restored_BKE_on'] = bool(restored[BDTR] & (1<<12))
                report['restored_AOE_off'] = not bool(restored[BDTR] & (1<<14))
                report['pass'] = report['pass'] and all(report[k] for k in
                    ('restored_exact_AF1', 'restored_MOE_off', 'restored_BKE_on', 'restored_AOE_off'))
            except Exception as exc:
                report['restore_error'] = str(exc)
                report['pass'] = False
        h.close()
        report['motor_commands_sent'] = commands
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:report.get(k) for k in ('pass','rx_overflow_reproduced','new_errors',
        'break_flag_observed','restored_exact_AF1','error','restore_error')}, indent=2))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
