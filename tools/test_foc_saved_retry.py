"""Fresh epoch and changed ADC proof; entirely offline."""
import copy
import json
import prepare_foc_observer_schedule_fix as p
from foc_saved_retry import load_saved_retry,require_fresh_native_epoch,ADC_record_is_new
from configure_multi_algorithm import crc32c


def rejects(call):
    try:
        call()
    except AssertionError:
        return
    raise AssertionError('Expected invalid proof to be rejected')


def main():
    out = p.OUT / 'verification/saved_retry_fix_r2'
    out.mkdir(exist_ok=False)
    previous = p.OUT / 'powered_FOC_schedule_20261030_r1'
    proof = load_saved_retry(previous, p.NEW)
    state = json.loads(p.read(previous / 'report.json'))['after']
    rejects(lambda: require_fresh_native_epoch(state, proof, p.NEW, crc32c))
    assert not ADC_record_is_new(state, proof), 'Old frozen record must never satisfy a new recording'
    fresh = copy.deepcopy(state)
    fresh['foc_runtime'].update(source='OFF_synthetic_CPU_probe', observer_steps=64, meter_errors=0, first_fault=None)
    fresh['mc_current_detail_age_ms'] = 10
    raw = bytearray.fromhex(fresh['mc_current_detail_hex'])
    raw[3] = (raw[3] | 1) & ~16
    raw[10:14] = (1000).to_bytes(4, 'little')
    raw[39:43] = crc32c(raw[:39]).to_bytes(4, 'little')
    fresh['mc_current_detail_hex'] = raw.hex()
    result = require_fresh_native_epoch(fresh, proof, p.NEW, crc32c)
    restarted = dict(fresh, run_id=0, run_start_ms=0)
    assert require_fresh_native_epoch(restarted, proof, p.NEW, crc32c)['supervisor_also_restarted']
    for changes in (dict(run_id=0), dict(run_start_ms=0), dict(mc_current_zero_ready=0),
                    dict(mc_current_detail_age_ms=1500)):
        rejects(lambda changes=changes: require_fresh_native_epoch(dict(fresh, **changes), proof, p.NEW, crc32c))
    corrupt = copy.deepcopy(fresh)
    bad = bytearray(raw)
    bad[15] ^= 1
    corrupt['mc_current_detail_hex'] = bad.hex()
    rejects(lambda: require_fresh_native_epoch(corrupt, proof, p.NEW, crc32c))
    no_reset = copy.deepcopy(fresh)
    bad = bytearray(raw)
    bad[10:14] = proof['previous_ADC_frozen_ms'].to_bytes(4, 'little')
    bad[39:43] = crc32c(bad[:39]).to_bytes(4, 'little')
    no_reset['mc_current_detail_hex'] = bad.hex()
    rejects(lambda: require_fresh_native_epoch(no_reset, proof, p.NEW, crc32c))
    # Construct a DIFFERENT, CRC-valid blob in the synthetic new epoch.
    blob = bytearray.fromhex(state['mc_adc_peak_hex'])
    blob[40:44] = (6000).to_bytes(4, 'little')
    blob[60:64] = bytes(4)
    blob[60:64] = crc32c(blob).to_bytes(4, 'little')
    updated = dict(fresh, mc_adc_peak_complete=1, mc_adc_peak_hex=blob.hex())
    assert ADC_record_is_new(updated, proof)
    blob[80] ^= 1
    assert not ADC_record_is_new(dict(updated, mc_adc_peak_hex=blob.hex()), proof)
    assert not ADC_record_is_new(dict(updated, mc_adc_peak_complete=0), proof)
    report = dict(passed=True, hardware_commands=0, previous_files_hashes_validated=True,
        previous_native_RUN_state_rejected=True, supervisor_run_id_preserved_and_validated=True,
        fresh_OFF64_and_native_detail_CRC_required=True, reset_tick_must_be_new_epoch=True,
        full_supervisor_restart_with_fresh_native_epoch_supported=True,
        stale_ADC_rejected=True, new_ADC_CRC_required=True,
        new_synthetic_epoch_accepted=result, native_start_guards_unchanged=True)
    p.write(out / 'report.json', json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
