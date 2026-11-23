"""Bounded auxiliary-only external SD test; restore the verified production image."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from physical_sd_waveform import physical_sd_checks
from run_current_pwm_801 import verified_images
from run_mcsdk_logic_bench import PROGRAMMER, SERIAL, DEVICE, compare_code_sections, waveform
from run_wifi_nucleo_pwm_bench import (
    WifiHmi, analyze_static, capture, read_control_token, run_logged, sha256, wait_status,
)
from saleae_pwm_analyze import load_csv, channel_summary
from verify_wifi_command_path import get_wifi_logs
from wifi_bench_scenarios import operator_keepalive, outputs_off
from wifi_stop_tail_probe import parse_registers

PRODUCTION = 2026100801
FIXTURE = 2026100899
UNO = 2026100804


def safe_status(s, build, *, expected_armed=0):
    try:
        integers = ('pwm', 'hmi_hv_armed', 'estop', 'fw_build', 'mc_fw_build',
                    'bp_vbus_valid', 'bp_status', 'bp_vbus_raw', 'precharge', 'pfc', 'brake', 'bp_ext')
        if any(type(s.get(k)) is not int for k in integers):
            return False
        return (outputs_off(s) and s['state'] == 'SAFE' and s['hmi_hv_armed'] == expected_armed and s['estop'] == 0
                and (s['fw_build'], s['mc_fw_build']) == (UNO, build)
                and 0 <= s['bp_age_ms'] < 300
                and s['bp_vbus_valid'] == 1 and 0 <= s['bp_vbus_age_ms'] < 300
                and 0 <= s['vdc'] <= 10 and 0 <= s['bp_vbus_raw'] <= 100
                and not(s['bp_status'] & 0x22)
                and all(s.get(k) == 0 for k in ('precharge', 'pfc', 'brake', 'bp_ext')))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def restart_probe_allowed(trip_pass, s):
    return (trip_pass is True and outputs_off(s) and s.get('mc_diag_valid') == 1
            and bool(s.get('mc_fault_occurred_mask', 0)&0x400)
            and s.get('bp_fault', 0) != 0 and s.get('hmi_hv_armed') == 0)


def wait_for_go(timeout_s=60):
    signal = threading.Event()
    answer = []

    def reader():
        for line in sys.stdin:
            if line.strip() == 'GO':
                answer.append('GO')
                signal.set()
                return
        signal.set()

    threading.Thread(target=reader, daemon=True).start()
    if not signal.wait(timeout_s) or answer != ['GO']:
        raise RuntimeError('GO not received; aborting before ARM/START')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-j1-disconnected', action='store_true')
    p.add_argument('--confirm-motor-disconnected', action='store_true')
    p.add_argument('--confirm-j4-aux-only', action='store_true')
    p.add_argument('--fixture', type=Path, required=True)
    p.add_argument('--outdir', type=Path, required=True)
    p.add_argument('--countdown-s', type=int, choices=range(3, 16), default=5,
                   help='Preparation countdown before START; does not extend the 3 s PWM limit')
    p.add_argument('--confirm-pc8-test-wire', action='store_true',
                   help='Temporary PC8/CN10-2 -> 1k -> STEVAL TP23 wire installed; not a permanent connection')
    p.add_argument('--gui-capture', action='store_true',
                   help='Visible GUI owns continuous acquisition; waveform qualification is pending saved GUI data')
    args = p.parse_args()
    if not (args.confirm_j1_disconnected and args.confirm_motor_disconnected and args.confirm_j4_aux_only):
        p.error('Physical J1/motor disconnection and auxiliary-only J4 confirmation required')
    root = Path(__file__).resolve().parents[1]
    fixture = args.fixture.resolve(strict=True)
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    logs = out / 'logs'
    logs.mkdir()
    fm = json.loads((fixture/'fixture_manifest.json').read_text())
    auto_sd = fm.get('fixture_variant') == 'auxiliary_only_10v_auto_sd_pc8'
    if auto_sd and not args.confirm_pc8_test_wire:
        p.error('Automatic fixture requires operator confirmation of PC8 -> 1k -> TP23 wire')
    if (fm.get('pass') is not True or fm.get('fixture_variant') not in
            ('auxiliary_only_10v', 'auxiliary_only_10v_auto_sd_pc8')
            or fm.get('fixture_mcsdk_filtered_voltage_limit_v') != 10
            or (fm.get('production_build'), fm.get('bench_build')) != (PRODUCTION, FIXTURE)):
        raise RuntimeError('Wrong fixture provenance or bus limit')
    host = json.loads((fixture.parent/'interlock_10v/report.json').read_text())
    if host.get('pass') is not True or host.get('fixture_bus_limit_v') != 10:
        raise RuntimeError('10 V host interlock evidence required')
    production = root/'firmware/updates/installed_804_801/nucleo'
    prod_hex, prod_bin = verified_images(production, PRODUCTION)
    bench_build = fixture/'project/STM32CubeIDE/Debug'
    bench_hex, bench_bin = verified_images(bench_build, FIXTURE)
    prod_build = root/'mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV/STM32CubeIDE/Debug'
    if sha256(prod_build/prod_hex.name) != sha256(prod_hex):
        raise RuntimeError('Production code-equivalence build differs from restore image')
    for relative, hashes in fm['changed_files'].items():
        if sha256(fixture/'project'/relative) != hashes['bench_sha256']:
            raise RuntimeError('Fixture source changed after preparation: '+relative)
    report = {'pass': False, 'scope': 'Auxiliary-only external SD test, not HV/IPM intrinsic OC/UVLO qualification',
              'hardware_acceptance': False, 'hv_release_approved': False,
              'fixture_variant': fm['fixture_variant'], 'restored': False, 'commands': [],
              'images': {'production_bin': sha256(prod_bin), 'fixture_bin': sha256(bench_bin)},
              'software_break_injected': False, 'production_active_pwm_tested': False}
    report['external_stimulus'] = fm.get('external_stimulus')
    report['acquisition_owner'] = 'visible_GUI_Looping' if args.gui_capture else 'automation_API_timed'
    token = read_control_token('adb', '3880458060', '/home/arduino/.config/mic-ai/control_token')
    h = WifiHmi('http://192.168.1.138:8080', token, report['commands'], via_wsl=True)
    modified = False

    def cli(extra, label, hotplug=False):
        run_logged([PROGRAMMER, '-c', 'port=SWD', 'mode='+('HOTPLUG' if hotplug else 'UR'),
                    *([] if hotplug else ['reset=HWrst']), 'sn='+SERIAL, *extra], logs/label, timeout=60)

    def program(image, binary, label):
        cli(['-w', str(image), '-v', '-rst'], label+'_flash.log')
        readback = out/(label+'_readback.bin')
        try:
            cli(['-u', '0x08000000', str(binary.stat().st_size), str(readback)], label+'_readback.log')
            if readback.read_bytes() != binary.read_bytes():
                raise RuntimeError('Readback differs from image: '+label)
        finally:
            cli(['-rst'], label+'_reset.log')
        report[label+'_readback_match'] = True

    def calibration_hash():
        result = subprocess.run(['adb', '-s', '3880458060', 'shell', 'sha256sum',
                                 '/home/arduino/.config/mic-ai/vbus_calibration.json'],
                                capture_output=True, text=True, check=True, timeout=10)
        digest = result.stdout.split()[0]
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise RuntimeError('Calibration digest unavailable')
        return digest

    try:
        report['before'] = h.status()
        if not safe_status(report['before'], PRODUCTION):
            raise RuntimeError('Production must be disarmed SAFE with reported bus <=10 V')
        report['calibration_before_sha256'] = calibration_hash()
        report['code_equivalence'] = compare_code_sections(prod_build, bench_build, out/'code_equivalence')
        if not report['code_equivalence']['pass']:
            raise RuntimeError('PWM/BKIN code differs from production')
        from saleae import automation
        with automation.Manager.connect(port=10430) as manager:
            if not any(d.device_id == DEVICE and not d.is_simulation for d in manager.get_devices()):
                raise RuntimeError('Physical Saleae absent')
            h.post('/api/stop-sequence', {'emergency': False}, 'preflash STOP')
            modified = True
            program(bench_hex, bench_bin, 'fixture')
            wait_status(h, lambda s: safe_status(s, FIXTURE) and s.get('bp_softstart_ready') == 1,
                        15, 'real ADC in auxiliary fixture range')
            h.command('CLEAR')
            report['clean_fixture'] = wait_status(h, lambda s: safe_status(s, FIXTURE)
                and s.get('bp_fault') == 0 and s.get('bp_clear_pending') == 0,
                8, 'fixture SAFE with no fault')
            h.post('/api/arm-profile', {'profile': 'lv'}, 'select bounded LV profile')
            configured = h.status()
            if configured.get('hmi_start_runlimit_s') != 3 or configured.get('hmi_hv_max_vdc') != 10:
                raise RuntimeError('Expected unchanged HMI 3 s / 10 V limits')
            if args.gui_capture:
                cli(['-r32', '0x48000010', '4', '-r32', '0x40012c44', '4'],
                    'gui_prestart_registers.log', hotplug=True)
                words = parse_registers((logs/'gui_prestart_registers.log').read_text())
                report['sd_before_high'] = bool(words[0x48000010] & (1 << 6))
                if not report['sd_before_high'] or words[0x40012c44] & 0x8000:
                    raise RuntimeError('Physical SD must be HIGH and MOE off')
            else:
                idle = capture(manager, DEVICE, out/'before_capture', .12, 4_000_000)
                report['idle_outputs'] = analyze_static(idle, sample_rate_hz=4_000_000)
                t, v = load_csv(idle, list(range(7)))
                report['sd_before'] = channel_summary(t, v[6])
                if not report['idle_outputs']['pass'] or not all(v[6]):
                    raise RuntimeError('Outputs must be LOW, physical SD HIGH; do not touch resistor yet')
            print('READY_FOR_GO: no PWM yet; stdin GO starts one bounded trial', flush=True)
            wait_for_go()
            if not safe_status(h.status(), FIXTURE):
                raise RuntimeError('State changed while waiting for GO')
            with operator_keepalive(h) as heartbeat:
                h.command('MODE VF')
                h.command('SET FREQ 5')
                h.post('/api/hv-arm', {'action': 'arm', 'confirm': 'ARM LV HV OFF'}, 'auxiliary LV ARM')
                for remaining in range(args.countdown_s, 0, -1):
                    print(f'COUNTDOWN {remaining}: contact only after PWM starts', flush=True)
                    time.sleep(1)
                if not safe_status(h.status(), FIXTURE, expected_armed=1):
                    raise RuntimeError('Fixture state changed during countdown')
                folder = out/'physical_sd_capture'
                folder.mkdir()
                acquisition = nullcontext(None) if args.gui_capture else manager.start_capture(device_id=DEVICE,
                        device_configuration=automation.LogicDeviceConfiguration(
                            enabled_digital_channels=list(range(7)), digital_sample_rate=4_000_000),
                        capture_configuration=automation.CaptureConfiguration(
                            capture_mode=automation.TimedCaptureMode(duration_seconds=6)))
                with acquisition as session:
                    time.sleep(.2)
                    h.post('/api/start-sequence', {}, 'captured physical SD START')
                    report['active'] = wait_status(h, lambda s: s.get('pwm') == 1
                        and bool(s.get('bp_status', 0)&0x20) and s.get('mc_fw_build') == FIXTURE,
                        1.5, 'actual fixture PWM flag')
                    print('PWM_ACTIVE: '+('automatic external PC8 pulse pending; do not touch wires' if auto_sd
                                          else 'external resistor contact now; hold about 1 second then release'), flush=True)
                    if args.gui_capture:
                        report['gui_off_status'] = wait_status(h, outputs_off, 5, 'bounded GUI trial off')
                        time.sleep(.3)
                    else:
                        session.wait()
                        session.save_capture(str(folder/'capture.sal'))
                        session.export_raw_data_csv(directory=str(folder/'csv'), digital_channels=list(range(7)))
                # No software STOP/BG is injected before completion of this waveform.
                # Independent HMI/MCU run limits remain active and are not extended.
                if args.gui_capture:
                    report['waveform_pending'] = True
                    report['physical_trip'] = {'pass': False, 'pending': 'saved GUI waveform required'}
                    report['pwm'] = {'pass': False, 'pending': 'saved GUI waveform required'}
                else:
                    csv = folder/'csv/digital.csv'
                    times, values = load_csv(csv, list(range(7)))
                    report['physical_trip'] = physical_sd_checks(times, values)
                    report['pwm'] = waveform(csv, 4_000_000, 16000, 1.35e-6,
                                              settled=False, require_sd_high=False)
                report['after_trip'] = h.status()
                # A missed contact is not a negative START test: the arm may still
                # be valid. Never issue a second START without a measured trip.
                if restart_probe_allowed(report['physical_trip']['pass'], report['after_trip']):
                    code, response = h.request('POST', '/api/start-sequence', {})
                else:
                    code, response = 0, {'ok': False, 'error': 'skipped: no qualified latched physical trip'}
                report['restart_rejected'] = {'http_status': code, 'ok': response.get('ok'),
                    'error': response.get('error'), 'scope': 'HMI rejection; not a direct MCU retry bypass'}
                report['heartbeat'] = heartbeat
                after = report['after_trip']
                report['checks'] = {
                    'physical_waveform': report['physical_trip']['pass'],
                    'production_carrier_and_deadtime': report['pwm']['pass'],
                    'outputs_off_after_trip': outputs_off(after),
                    'physical_driver_fault_latched': after.get('mc_diag_valid') == 1
                        and bool(after.get('mc_fault_occurred_mask', 0)&0x400),
                    'no_UART_hardware_error': after.get('mc_uart_error_flags') == 0,
                    'HMI_restart_rejected': code == 409 and response.get('ok') is False,
                    'heartbeat_no_errors': not heartbeat['errors'],
                }
                report['test_pass'] = all(report['checks'].values())
    except BaseException as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'
        print('TEST_ERROR: '+report['error'], flush=True)
    finally:
        report['final_stop_http'] = h.fail_safe_stop()[0]
        if modified:
            try:
                h.command('CLEAR')
                wait_status(h, lambda s: safe_status(s, FIXTURE) and s.get('bp_fault') == 0,
                            5, 'SD released for profile restoration')
                h.post('/api/arm-profile', {'profile': 'hv'}, 'restore HV profile while disarmed')
            except Exception as exc:
                report['profile_restore_error'] = str(exc)
            try:
                program(prod_hex, prod_bin, 'production')
                report['restored'] = True
                report['final_status'] = wait_status(h, lambda s: safe_status(s, PRODUCTION),
                                                     20, 'production 801 restored SAFE')
                report['calibration_after_sha256'] = calibration_hash()
                report['calibration_preserved'] = report['calibration_after_sha256'] == report['calibration_before_sha256']
                report['hv_profile_restored'] = report['final_status'].get('hmi_arm_profile') == 'hv'
            except Exception as exc:
                report['restore_error'] = str(exc)
        try:
            text = get_wifi_logs(h, token)
            if token in text:
                raise RuntimeError('Credential in logs; not saving')
            (out/'wifi_logs.txt').write_text(text, encoding='utf-8')
        except Exception as exc:
            report['log_error'] = str(exc)
        h.close()
        report['pass'] = (report.get('test_pass') is True and report['restored']
                          and report.get('calibration_preserved') is True
                          and report.get('hv_profile_restored') is True
                          and report['final_stop_http'] == 200)
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({k: report.get(k) for k in ('pass', 'checks', 'error', 'restored',
              'restore_error', 'profile_restore_error', 'calibration_preserved', 'hv_profile_restored')}, indent=2), flush=True)
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
