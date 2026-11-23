"""One confirmed 3005/3006 FOC 5 Hz / 5 s trial, unchanged protections."""
import run_foc_runtime_trial as trial
import prepare_foc_regular_adc_fix as package

trial.PAIR = package.NEW
trial.__doc__ = __doc__

if __name__ == '__main__':
    raise SystemExit(trial.main())
