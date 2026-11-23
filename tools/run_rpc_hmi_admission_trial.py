"""Uno1609/Nucleo1606: one authorized FOC5Hz/5s trial, unchanged motor guards."""
import json
import prepare_rpc_short_lock as package
import prepare_rpc_hmi_admission as hmi
import run_telemetry_deadline_trial as runner
from release_observer_decoder import load_decoder

runner.p=package
runner.driver.package=package
runner.driver.trial.PAIR=package.NEW
runner.driver.boot.package=package
runner.driver.boot.trial=runner.driver.trial
runner.driver.capture.package=package
runner.driver.capture.base=runner.driver.boot
runner.driver.capture.decode_observer_trace_hex=load_decoder(hmi.OUT)


def main():
    accepted=json.loads((hmi.OUT/'acceptance.json').read_text(encoding='utf8'))
    assert accepted['long_idle_passed'] and accepted['Linux_server_readback_verified']
    assert accepted['firmware_pair']==list(package.NEW)
    assert accepted['protection_limits']==dict(OFF_fast_cycles=4000,estimate_ms=2,trip_A=1.35,ADC_ticks=2048)
    return runner.main()


if __name__=='__main__':raise SystemExit(main())
