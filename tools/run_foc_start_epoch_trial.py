"""One guarded 2961/2962 FOC trial against this boot's retained SD evidence."""
import run_estimated_foc_first_trial as trial
import prepare_foc_start_epoch_fix as package
trial.PAIR=package.NEW
trial.SD_PROOF=package.OUT/'autonomous_before_FOC_r2'
if __name__=='__main__':raise SystemExit(trial.main())
