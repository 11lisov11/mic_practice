"""One confirmed3007/3008 FOC5Hz/5s trial with exact ADC fault capture."""
import run_foc_runtime_trial as trial
import prepare_foc_cache_snapshot_fix as package

trial.PAIR = package.NEW
trial.__doc__ = __doc__

if __name__ == '__main__':
    raise SystemExit(trial.main())
