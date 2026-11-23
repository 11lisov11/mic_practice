"""Validate an explicitly requested repeat after a fresh Nucleo epoch.

The supervisor's run_id can persist while Nucleo is reset. All native START
guards and the fresh OFF64 timing requirement remain in the trial runner.
"""
import hashlib
import json
import math
from pathlib import Path


def load_saved_retry(directory, pair, allow_saved_current_trip=False):
    directory = Path(directory).resolve()
    hashes = json.loads((directory / 'saved_files_sha256.json').read_text(encoding='utf-8'))
    for name, digest in hashes.items():
        path = (directory / name).resolve()
        assert path.parent == directory, 'Previous evidence path escapes its directory'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
    report = json.loads((directory / 'report.json').read_text(encoding='utf-8'))
    s = report['after']
    assert report['pair'] == list(pair) and report['start_commands'] == 1
    assert report['prior_SD_record_retained'] and report['runtime_record_received'] and report['ADC_record_received']
    assert s['state'] == 'SAFE' and s['pwm'] == 0
    first = s['foc_runtime']['first_fault']
    host_stop = (s['algorithm_fault'] == 0 and first is None
                 and s['mc_fault_current_mask'] == s['mc_fault_occurred_mask'] == 0
                 and s['mc_fault_reason'] == 4 and s['estop'] == 1)
    current_trip = False
    if not host_stop and allow_saved_current_trip:
        assert s['algorithm_fault'] == 2 and first is not None
        assert first['reason_code'] == 7 and first['algorithm_fault'] == 2
        assert s['mc_fault_current_mask'] == s['mc_fault_occurred_mask'] == 1
        assert s['mc_sd_live']['level'] == 'HIGH' and s['mc_sd_live']['break_irq_enabled']
        for key in ('mc_uart_error_flags', 'mc_transport_fault', 'mc_bad_integrity', 'mc_bad_sequence'):
            assert s[key] == 0, key
        row = next(x for x in s['mc_adc_peak']['samples'] if x['cycles'] == first['adc_cycles'])
        assert row['accepted_by_monitor'] and row['epoch_consistent'] and row['timer_cnt_at_update'] < 2048
        assert first['adc_age_us'] < 187.5 and first['estimate_age_us'] < 2000
        u, v, _ = row['counts_uvw']
        scale = 3.3 / (4095 * .04 * 2.1)
        vector = math.hypot(u * scale, (u + 2 * v) * scale / math.sqrt(3))
        # This explicit repeat request concerns only the saved near-threshold
        # event. Larger or combined protection events are not eligible here.
        assert 1.35 < vector < 1.40
        current_trip = True
    assert host_stop or current_trip, 'Saved protection event is not eligible for this explicit repeat'
    raw = (directory / 'ADC_peak.bin').read_bytes()
    assert len(raw) == 1024 and raw == bytes.fromhex(s['mc_adc_peak_hex'])
    return dict(directory=str(directory), expected_idle_run_id=s['run_id'],
        expected_idle_start_ms=s['run_start_ms'],
        previous_native_fw=pair[1],
        saved_current_trip=current_trip, fresh_epoch_validated=False,
        previous_ADC_sha256=hashlib.sha256(raw).hexdigest(),
        previous_ADC_frozen_ms=s['mc_adc_peak']['frozen_ms'])


def require_fresh_native_epoch(s, proof, pair, crc32c):
    same_supervisor = (s['run_id'] == proof['expected_idle_run_id']
                       and s['run_start_ms'] == proof['expected_idle_start_ms'])
    fresh_supervisor = s['run_id'] == s['run_start_ms'] == 0
    assert same_supervisor or fresh_supervisor, 'Unexpected supervisor trial history'
    runtime = s.get('foc_runtime') or {}
    assert runtime.get('source') == 'OFF_synthetic_CPU_probe' and runtime.get('observer_steps') == 64
    assert runtime.get('first_fault') is None and runtime.get('meter_errors') == 0
    assert s['mc_current_zero_ready'] == 1 and 0 <= s['mc_current_detail_age_ms'] < 1500
    raw = bytes.fromhex(s['mc_current_detail_hex'])
    assert len(raw) == 43 and raw[:3] == bytes([0x55, 0xaa, 0xd6]) and raw[38] == 1
    assert int.from_bytes(raw[6:10], 'little') == pair[1]
    assert crc32c(raw[:39]) == int.from_bytes(raw[39:], 'little')
    assert raw[3] & 1 and not raw[3] & 16
    tick = int.from_bytes(raw[10:14], 'little')
    if proof.get('saved_current_trip'):
        # The first native fault survives STOP/CLEAR and prepare. Its removal,
        # followed by the boot-only OFF64 probe, establishes a fresh native
        # epoch even if the operator waited longer than the previous uptime.
        assert runtime['first_fault'] is None and runtime['source'] == 'OFF_synthetic_CPU_probe'
        assert s['algorithm_fault'] == s['mc_fault_current_mask'] == s['mc_fault_occurred_mask'] == 0
    else:
        assert tick < proof['previous_ADC_frozen_ms'], 'Fresh Nucleo epoch has not been established'
    proof['fresh_epoch_validated'] = True
    return dict(validated=True, fresh_detail_tick_ms=tick,
        previous_frozen_ms=proof['previous_ADC_frozen_ms'], supervisor_run_id=s['run_id'],
        supervisor_also_restarted=fresh_supervisor,
        reset_evidence='immutable_fault_cleared_and_boot_OFF64' if proof.get('saved_current_trip') else 'new_native_uptime_and_boot_OFF64')


def ADC_record_is_new(s, proof):
    if s.get('mc_adc_peak_complete') != 1:
        return False
    if proof is None:
        return True
    raw = bytes.fromhex(s.get('mc_adc_peak_hex', ''))
    if len(raw) != 1024 or raw[:4] != b'APC1':
        return False
    from configure_multi_algorithm import crc32c
    if int.from_bytes(raw[8:12], 'little') != proof['previous_native_fw']:
        return False
    if crc32c(raw[:60] + bytes(4) + raw[64:]) != int.from_bytes(raw[60:64], 'little'):
        return False
    epoch_valid = (proof.get('fresh_epoch_validated', False) if proof.get('saved_current_trip')
                   else int.from_bytes(raw[40:44], 'little') < proof['previous_ADC_frozen_ms'])
    return (epoch_valid
            and hashlib.sha256(raw).hexdigest() != proof['previous_ADC_sha256'])
