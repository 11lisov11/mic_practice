"""One confirmed3003/3004 FOC5Hz/5s trial, original protections and STOP."""
import run_foc_runtime_trial as trial
import prepare_foc_update_latency_fix as package
trial.PAIR=package.NEW
trial.__doc__=__doc__
if __name__=='__main__':raise SystemExit(trial.main())
