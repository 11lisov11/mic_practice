"""1607/1606: explicitly authorized bounded FOC trial; unchanged motor guards."""
import prepare_rpc_route_recovery as package
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

if __name__=='__main__':raise SystemExit(runner.main())
