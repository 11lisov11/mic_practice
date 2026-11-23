"""One confirmed3009/3010 FOC5Hz/5s trial with frozen publication diagnostics."""
import run_foc_runtime_trial as trial
import prepare_foc_estimate_publish_fix as package

trial.PAIR = package.NEW
trial.__doc__ = __doc__

if __name__ == '__main__':
    raise SystemExit(trial.main())
