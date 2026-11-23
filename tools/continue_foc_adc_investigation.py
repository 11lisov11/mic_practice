"""Offline causal checks and mocked trial rehearsal; no hardware mutations."""
import contextlib
import copy
import hashlib
import io
import json
import math
import sys
from datetime import datetime
from unittest.mock import patch

import prepare_foc_regular_adc_fix as p
import run_foc_regular_adc_trial as run
from test_foc_runtime_trial_host import Network, FakeThread, FakeTimer


def main():
    out = p.OUT / ('continued_analysis_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    out.mkdir(exist_ok=False)

    def save(name, obj):
        p.write(out / name, json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

    def sha(f):
        return hashlib.sha256(f.read_bytes()).hexdigest()

    preserved = {}
    for name in ('verification/preserved_captures_sha256.json',
                 'installation_verified_r1/preserved_installation_evidence.json'):
        for rel, digest in json.loads(p.read(p.OUT / name)).items():
            assert rel not in preserved or preserved[rel] == digest
            preserved[rel] = digest
    for rel, digest in preserved.items():
        assert sha(p.ROOT / rel) == digest, rel
    for rel, digest in json.loads(p.read(p.OUT / 'source_hashes.json')).items():
        assert sha(p.OUT / rel) == digest, rel
    manifest = json.loads(p.read(p.OUT / 'manifest.json'))
    for rel, digest in manifest['artifacts'].items():
        assert sha(p.OUT / rel) == digest, rel
    assert manifest['installed'] and manifest['installation_readback_verified']
    assert run.trial.PAIR == p.NEW

    source = p.BASE / 'powered_FOC_CPU_IRQ_20261030_r2'
    rows = json.loads(p.read(source / 'ADC_peak_decoded.json'))['samples']
    before, fault = rows[9:11]
    assert before['pair'] == fault['pair'] == 1
    assert before['sequence'] + 1 == fault['sequence']
    dt = ((fault['cycles'] - before['cycles']) & 0xffffffff) / 170000000
    # Match the sealed ma_amps implementation (4095, not 4096).
    assert 'ADC_REFERENCE_VOLTAGE/(4095.0*RSHUNT*AMPLIFICATION_GAIN)' in p.read(p.OUT / 'nucleo/Src/multi_native.c')
    scale = 3.3 / (4095 * .04 * 2.1)
    phase_step = [(b-a)*scale for a,b in zip(before['counts_uvw'],fault['counts_uvw'])]
    ia = fault['counts_uvw'][0] * scale
    ibeta = (fault['counts_uvw'][0] + 2*fault['counts_uvw'][1]) * scale / math.sqrt(3)
    norm = math.hypot(ia, ibeta)
    replay = list(map(float, p.read(source / 'current_trip_replay.log').split()))
    assert replay[0] == 2 and abs(norm-replay[3]) < 1e-6
    norm = replay[3]  # authoritative result from the actual float32 C kernel
    # Independent observations are just U and W. V is reconstructed, so
    # U+V+W=0 is an identity and cannot validate this sample physically.
    assert sum(fault['counts_uvw']) == 0
    assert norm > 1.35
    save('causal_analysis.json', dict(
        source_capture=str(source / 'ADC_peak.bin'), sequence=fault['sequence'],
        delta_time_us=dt*1e6, ADC_raw_step=[b-a for a,b in zip(before['raw_adc'],fault['raw_adc'])],
        phase_step_A_nominal=phase_step, independent_phases=['U','W'],
        reconstructed_phase='V', phase_sum_zero_is_not_independent_validation=True,
        nominal_current_vector_A=norm, unchanged_trip_A=1.35,
        exceedance_A=norm-1.35, exceedance_percent=(norm/1.35-1)*100,
        update_count=fault['timer_cnt_at_update'], update_guard_ticks=2048,
        exact_physical_current_scale_not_qualified=True,
        regular_EOC_present_at_sequences=[r['sequence'] for r in rows if r['adc_isr'][0]&4],
        EOC_does_not_uniquely_identify_fault=True,
        real_current_vs_ADC_error_unresolved=True,
        independent_current_reference_missing=True,
        conclusion='Known ADC scheduling integration defect is fixed in installed3006; '
                   'old capture alone cannot establish that it caused this particular trip.',
        no_new_firmware_or_current_filter_needed_from_this_analysis=True))

    # Rehearse the actual runner against a fully mocked HTTP server. Its saved
    # base status is historical, never presented as a fresh hardware reading.
    base = json.loads(p.read(p.OUT / 'installation_verified_r1/final_status.json'))['data']
    assert (base['fw_build'], base['mc_fw_build']) == p.NEW
    fake_root = out / 'fake_workspace'
    (fake_root / '.unoq_ssh').mkdir(parents=True)
    (fake_root / '.unoq_ssh/control_token').write_text('unit-test-token', encoding='ascii')
    scenarios = {}
    cases = [('success', True), ('failed_clear', True), ('runtime_fault', True),
             ('success_without_clear', False), ('denied_clear', False),
             ('current_trip', False), ('wrong_pair', False), ('SD_low', False),
             ('UART_error', False), ('low_bus', False)]
    for case, allow_clear in cases:
        network = Network(case, base)
        if case == 'wrong_pair': network.base['mc_fw_build'] = p.NEW[1]-2
        if case == 'SD_low': network.base['mc_sd_live']['level'] = 'LOW'
        if case == 'UART_error': network.base['mc_uart_error_flags'] = 8
        if case == 'low_bus': network.base['vdc'] = 10
        original_open = network.open

        def mocked_open(request, timeout=None):
            response = original_open(request, timeout)
            if case == 'current_trip' and network.started:
                # A failed START acknowledgement/telemetry must STOP, not retry.
                data = json.loads(response.raw)
                if 'data' in data:
                    data['data']['algorithm_fault'] = 2
                    data['data']['mc_fault_current_mask'] = 1
                    response.raw = json.dumps(data).encode()
            return response

        clock = [0.]
        def now():
            clock[0] += .2
            return clock[0]

        argv = ['run_foc_regular_adc_trial.py', '--confirm-autonomous-powered',
                '--outdir', str(out / ('mock_' + case))]
        if allow_clear: argv.append('--clear-once')
        with patch.object(run.trial, 'ROOT', fake_root), patch.object(sys, 'argv', argv), \
             patch.object(run.trial.urllib.request, 'build_opener', return_value=network), \
             patch.object(network, 'open', side_effect=mocked_open), \
             patch.object(run.trial.threading, 'Thread', FakeThread), \
             patch.object(run.trial.threading, 'Timer', FakeTimer), \
             patch.object(run.trial.time, 'monotonic', side_effect=now), \
             patch.object(run.trial.time, 'sleep', return_value=None), \
             contextlib.redirect_stdout(io.StringIO()):
            rc = run.trial.main()
        report = json.loads(p.read(out / ('mock_' + case) / 'report.json'))
        starts = sum(path == '/api/start-sequence' for path,body in network.calls)
        clears = sum(body == {'cmd':'CLEAR'} for path,body in network.calls)
        assert starts <= 1 and clears <= 1
        if case.startswith('success'):
            assert rc == 0 and report['passed'] and starts == 1
        else:
            assert rc == 1 and not report['passed']
        if case in ('failed_clear','denied_clear','wrong_pair','SD_low','UART_error','low_bus'):
            assert starts == 0
        if case in ('runtime_fault','current_trip'):
            assert starts == 1 and network.stopped
        if not allow_clear: assert clears == 0
        scenarios[case] = dict(passed=True, simulated_START=starts, simulated_CLEAR=clears)

    save('preserved_records_sha256.json', preserved)
    result = dict(passed=True, pair=list(p.NEW), old_files_verified=len(preserved),
                  hardware_commands=0, fresh_hardware_status_obtained=False,
                  physical_5s_trial_not_yet_verified=True, mocked_HTTP_only=True,
                  runner='tools/run_foc_regular_adc_trial.py', scenarios=scenarios,
                  trip_A=1.35, ADC_guard_ticks=2048,
                  no_change_to_installed_sources=True)
    save('report.json', result)
    print(json.dumps(dict(output=str(out), **result)))


if __name__ == '__main__':
    main()
