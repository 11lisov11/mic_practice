"""Future explicitly authorized1601/1602 trial; no device action on import."""
import prepare_observer_adc_delivery as p
import run_observer_input_epoch_trial as driver
from release_observer_decoder import load_decoder

driver.package=p
driver.trial.PAIR=p.NEW
driver.boot.package=p
driver.boot.trial=driver.trial
driver.capture.package=p
driver.capture.base=driver.boot
driver.capture.decode_observer_trace_hex=load_decoder(p.OUT)


if __name__=='__main__':
    # The existing runner requires a fresh physical-state confirmation and
    # separate --clear-once authorization. Never invoke this for offline tests.
    raise SystemExit(driver.main())
