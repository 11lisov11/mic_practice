"""One authorized 3011/3012 FOC5Hz/5s trial; never retries START or CLEAR."""
import run_foc_runtime_trial as trial
import prepare_foc_observer_schedule_fix as package
trial.PAIR = package.NEW
trial.__doc__ = __doc__
if __name__ == '__main__':
    raise SystemExit(trial.main())
