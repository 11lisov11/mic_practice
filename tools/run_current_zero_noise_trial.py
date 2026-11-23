"""Use the existing bounded staged runner on2505/2506; preserve peak/zero evidence."""
import run_current_shunt_5_10_5 as trial
from prepare_current_zero_noise import NEW

trial.checks.PAIR=NEW
old_ready=trial.ready
def ready(s):
    return (old_ready(s) and s.get('mc_adc_peak_hex')=='-'
            and s.get('mc_adc_peak_good')==0 and s.get('mc_adc_peak_complete')==0)
trial.ready=ready

if __name__=='__main__':raise SystemExit(trial.main())
