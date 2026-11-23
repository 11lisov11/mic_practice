"""Strict full-RMS staged trial for2509/2510; no partial-coverage exception."""
import run_current_shunt_5_10_5 as trial
from prepare_current_adc_apex_fix import NEW
from current_zero_quality import ready as zero_ready

def ready(s):
    return (trial.checks.ready(s) and zero_ready(s) and trial.sd_high(s,True)
        and trial.checks.capture_free(s)
        and s.get('mc_sd_live',{}).get('capture_running') is True
        and s.get('mc_sd_live',{}).get('first_record_ready') is False
        and s.get('mc_adc_peak_hex')=='-' and s.get('mc_adc_peak_good')==0
        and s.get('mc_adc_peak_complete')==0)

trial.checks.PAIR=NEW
trial.zero_ok=zero_ready
trial.ready=ready

if __name__=='__main__':raise SystemExit(trial.main())
