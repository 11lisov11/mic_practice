"""Later explicitly authorized1801/1802 FOC5Hz/5s with exact source capture.

Import and --verify-package-only never access devices. Retains the tested
bounded trial, fresh RPC baseline, current/age/Break gates and auto-stop.
"""
import json
import prepare_exact_nis_input_release as p
import run_pair_noise_FOC_trial as prior
from release_observer_decoder import load_decoder

prior.p=p
prior.runner.p=p
prior.runner.driver.package=p
prior.runner.driver.trial.PAIR=p.NEW
prior.runner.driver.boot.package=p
prior.runner.driver.boot.trial=prior.runner.driver.trial
prior.runner.driver.capture.package=p
prior.runner.driver.capture.base=prior.runner.driver.boot
prior.runner.driver.capture.decode_observer_trace_hex=load_decoder(p.OUT)


def package_check():
    m=json.loads(p.read(p.OUT/'manifest.json'))
    a=json.loads(p.read(p.OUT/'installation_acceptance.json'))
    q=json.loads(p.read(p.OUT/'OFF_qualification.json'))
    assert m['built'] and m['pair']==a['pair']==list(p.NEW) and a['installed']
    assert a['native_readback_verified'] and a['uno_readback_verified'] and a['calibration_unchanged']
    assert q['pair']==list(p.NEW) and q['OFF_CPU_qualified'] and q['OFF_cases']==64
    assert 0<q['OFF_fast_cycles']<=4000 and q['OFF_fast_limit_cycles']==4000 and q['estimate_age_limit_ms']==2
    assert m['NIS_safety_guard_retained'] and m['observer_math_unchanged'] and m['protections_and_limits_unchanged']
    assert (m['current_trip_A'],m['OFF_fast_limit_cycles'],m['estimate_age_ms'],m['ADC_UPDATE_ticks'])==(1.35,4000,2,2048)
    assert m['NIS_limits']==[25,50] and m['full_RUN_existing_limit_cycles']==5312
    assert m['capture_schema']==3 and m['source_window_rows']==16 and m['raw_ring_rows']==60
    for file,base in ((p.OUT/'source_hashes.json',p.OUT),(p.OUT/'release/sha256.json',p.OUT/'release'),
                      (p.OUT/'preserved_inputs_sha256.json',p.ROOT)):
        for rel,h in json.loads(p.read(file)).items():assert p.sha(base/rel)==h,rel
    return m


prior.package_check=package_check


if __name__=='__main__':raise SystemExit(prior.main())
