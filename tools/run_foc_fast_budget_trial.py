"""One confirmed3001/3002 FOC5Hz/5s trial; original guards and STOP unchanged."""
import run_foc_runtime_trial as trial
import prepare_foc_fast_budget_fix as package
trial.PAIR=package.NEW
trial.__doc__=__doc__
if __name__=='__main__':raise SystemExit(trial.main())
