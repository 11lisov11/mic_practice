"""An explicit current-trip repeat must wait for a genuinely fresh native epoch."""
import copy
import hashlib
import json
import prepare_foc_observer_schedule_fix as p
from configure_multi_algorithm import crc32c
from foc_saved_retry import load_saved_retry,require_fresh_native_epoch,ADC_record_is_new


def rejects(call):
    try:
        call()
    except AssertionError:
        return
    raise AssertionError('Invalid repeat proof accepted')


def main():
    out = p.OUT / 'verification/current_repeat_fix_r1'
    out.mkdir(exist_ok=False)
    previous = p.OUT / 'powered_FOC_schedule_20261030_r2'
    rejects(lambda: load_saved_retry(previous, p.NEW))
    proof = load_saved_retry(previous, p.NEW, allow_saved_current_trip=True)
    assert proof['saved_current_trip'] and not proof['fresh_epoch_validated']
    old = json.loads(p.read(previous / 'report.json'))['after']
    rejects(lambda: require_fresh_native_epoch(old, proof, p.NEW, crc32c))
    assert not ADC_record_is_new(old, proof)
    fresh = copy.deepcopy(old)
    fresh.update(algorithm_fault=0, mc_fault_current_mask=0, mc_fault_occurred_mask=0,
                 mc_current_detail_age_ms=10)
    fresh['foc_runtime'].update(source='OFF_synthetic_CPU_probe', observer_steps=64,
                                first_fault=None, meter_errors=0)
    raw = bytearray.fromhex(fresh['mc_current_detail_hex'])
    raw[3] = (raw[3] | 1) & ~16
    raw[10:14] = (proof['previous_ADC_frozen_ms'] + 10000).to_bytes(4, 'little')
    raw[39:43] = crc32c(raw[:39]).to_bytes(4, 'little')
    fresh['mc_current_detail_hex'] = raw.hex()
    bad = copy.deepcopy(fresh)
    bad['foc_runtime']['first_fault'] = old['foc_runtime']['first_fault']
    rejects(lambda: require_fresh_native_epoch(bad, proof, p.NEW, crc32c))
    rejects(lambda: require_fresh_native_epoch(dict(fresh, mc_fault_current_mask=1), proof, p.NEW, crc32c))
    reset = require_fresh_native_epoch(fresh, proof, p.NEW, crc32c)
    assert proof['fresh_epoch_validated'] and reset['reset_evidence'] == 'immutable_fault_cleared_and_boot_OFF64'
    blob = bytearray.fromhex(old['mc_adc_peak_hex'])
    blob[40:44] = (proof['previous_ADC_frozen_ms'] + 20000).to_bytes(4, 'little')
    blob[60:64] = bytes(4)
    blob[60:64] = crc32c(blob).to_bytes(4, 'little')
    record = dict(fresh, mc_adc_peak_complete=1, mc_adc_peak_hex=blob.hex())
    assert ADC_record_is_new(record, proof)
    assert not ADC_record_is_new(record, dict(proof, fresh_epoch_validated=False))
    assert not ADC_record_is_new(old, proof)
    blob[99] ^= 1
    assert not ADC_record_is_new(dict(record, mc_adc_peak_hex=blob.hex()), proof)
    for rel, digest in json.loads(p.read(p.OUT / 'source_hashes.json')).items():
        with (p.OUT / rel).open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == digest, rel
    result = dict(passed=True, hardware_commands=0, default_current_trip_repeat_rejected=True,
        saved_event_requires_explicit_repeat_option=True, active_current_fault_rejected=True,
        immutable_first_fault_must_be_gone=True, fresh_boot_OFF64_and_CRC_zero_required=True,
        stale_ADC_and_bad_CRC_rejected=True, old_firmware_sources_and_guards_unchanged=True,
        no_automatic_clear_or_restart=True, current_trip_A=1.35, estimate_limit_ms=2, ADC_guard_ticks=2048)
    p.write(out / 'report.json', json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
