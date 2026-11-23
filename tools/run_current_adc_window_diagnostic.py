"""One2507/2508 raw-ADC trial. Incomplete RMS remains invalid, hardware gates retained.

Diagnostic policy permits fresh windows at75..94% coverage without claiming RMS.
75% is the existing density floor12/16 samples/ms, not an RMS qualification.
ADC rails/clipping, stale data, zero failure, transport, SD, drive faults and
watchdogs still stop the trial. No firmware, calibration or MCU thresholds change.
"""
import math
import run_current_shunt_5_10_5 as trial
from current_zero_quality import ready as zero_ready

PAIR=(2026102507,2026102508)

def ready(s):
    return (trial.checks.ready(s) and zero_ready(s) and trial.sd_high(s,True)
        and trial.checks.capture_free(s)
        and s.get('mc_sd_live',{}).get('capture_running') is True
        and s.get('mc_sd_live',{}).get('first_record_ready') is False
        and s.get('mc_adc_peak_hex')=='-' and s.get('mc_adc_peak_good')==0
        and s.get('mc_adc_peak_complete')==0)

def measurement_healthy(s):
    try:
        flags=s['mc_current_flags'];coverage=s['mc_current_coverage_pct']
        if not (type(flags) is int and type(coverage) is int and 75<=coverage<=100
            and flags&1 and flags&8 and not (flags&(4|16|32))
            and 199<=s['mc_current_window_ms']<=220
            and 0<=s['mc_current_age_ms']<750
            and 0<=s['mc_current_detail_age_ms']<1500
            and 0<=s['mc_current_quality_age_ms']<1500
            and s.get('mc_current_bad')==0):return False
        valid=s['mc_current_telemetry_valid']
        if valid==0:
            return (not flags&2 and s['mc_current_rms_a'] is None
                and s['mc_current_peak_a'] is None and s['mc_current_instant_a'] is None)
        if valid!=1 or not flags&2 or coverage<95:return False
        for key in ('mc_current_rms_a','mc_current_peak_a','mc_current_instant_a'):
            a=s[key]
            if not isinstance(a,list) or len(a)!=3 or not all(type(v) in (int,float) and math.isfinite(v) for v in a):return False
        return True
    except (KeyError,TypeError,ValueError):return False

def current_at_target(s,target):
    return (measurement_healthy(s) and s.get('pwm')==1
        and s.get('mc_frequency_reference_valid')==1
        and abs(s.get('mc_frequency_reference_hz',-1)-target)<=.11)

trial.checks.PAIR=PAIR
trial.zero_ok=zero_ready
trial.ready=ready
trial.measurement_healthy=measurement_healthy
trial.current_at_target=current_at_target
trial.MEASUREMENT_POLICY='raw_adc_diagnostic_min75pct_density_no_invalid_rms_claim'

if __name__=='__main__':raise SystemExit(trial.main())
