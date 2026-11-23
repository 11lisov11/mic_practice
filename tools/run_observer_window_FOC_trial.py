"""One expressly authorized1611/1612 FOC5Hz/5000ms; independent MCU auto-stop.

No device calls on import. Retains established native/host guards and binds the
OFF-only collector to the installed schema3 decoder. No automatic retry.
"""
import json
import prepare_observer_current_window as package
import run_telemetry_deadline_trial as runner
from release_observer_decoder import load_decoder

runner.p=package
runner.driver.package=package
runner.driver.trial.PAIR=package.NEW
runner.driver.boot.package=package
runner.driver.boot.trial=runner.driver.trial
runner.driver.capture.package=package
runner.driver.capture.base=runner.driver.boot
runner.driver.capture.decode_observer_trace_hex=load_decoder(package.OUT)

def package_check():
    m=json.loads(package.read(package.OUT/'manifest.json'))
    assert m['installed'] and m['built'] and m['pair']==list(package.NEW)
    assert m['control_and_observer_Q_R_math_unchanged']
    assert (m['OFF_fast_budget_cycles'],m['estimate_age_limit_ms'],m['raw_trip_A'],m['ADC_UPDATE_limit_ticks'])==(4000,2,1.35,2048)
    assert m['RUN_existing_deadline_cycles']==5312
    for rel,h in json.loads(package.read(package.OUT/'source_hashes.json')).items():assert package.sha(package.OUT/rel)==h,rel
    for rel,h in m['artifacts'].items():assert package.sha(package.OUT/rel)==h,rel
    for rel,h in json.loads(package.read(package.OUT/'preserved_all_hashes.json')).items():assert package.sha(package.ROOT/rel)==h,rel
    return m

def main():
    package_check()
    return runner.main()

if __name__=='__main__':raise SystemExit(main())
