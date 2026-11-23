"""Strict RMS trial retaining the explicitly archived pre-START SD record.

No CLEAR/RESET/firmware change. Only waveform-memory availability differs from
the free-recorder wrapper; SDHIGH, BKE/config, BIE and all fault gates remain.
"""
import hashlib
import json
import math
import sys
import run_current_adc_apex_trial as strict
from run_current_shunt_5hz import archive_before_start
from prepare_current_adc_apex_fix import OUT

trial=strict.trial
ARCHIVE=json.loads((OUT/'prestart_sd_event_r1/report.json').read_text(encoding='utf-8'))
ACK=json.loads((OUT/'prestart_sd_ack_r1/report.json').read_text(encoding='utf-8'))
assert ACK['passed'] and ACK['clear_commands']==1 and ACK['motor_commands']==0

def retained(s):
    try:
        text=s.get('mc_break_wave_hex','-')
        return text!='-' and hashlib.sha256(bytes.fromhex(text)).hexdigest()==ARCHIVE['wave_sha256']
    except (ValueError,TypeError):return False

def ready(s):
    if not (trial.checks.ready(s) and strict.zero_ready(s) and trial.sd_high(s,True)
        and retained(s) and archive_before_start(s)):return False
    records={x.get('kind'):x for x in s.get('mc_break_snapshots',[])}
    first=records.get('first_since_boot',{});start=records.get('first_start_window',{})
    raw=first.get('raw',{});q=s.get('mc_sd_live',{})
    return (first.get('available') is True and start.get('available') is True
        and start.get('captured') is False and raw.get('tick_ms')==ARCHIVE['event_tick_ms']
        and raw.get('current_faults')==0 and raw.get('occurred_faults')==0
        and q.get('first_record_ready') is True and q.get('capture_running') is False
        and s.get('mc_adc_peak_hex')=='-' and s.get('mc_adc_peak_good')==0
        and s.get('mc_adc_peak_complete')==0)

original_active=trial.active
def active(s,target):
    return original_active(s,target) and retained(s)

def measurement_healthy(s):
    try:
        flags=s['mc_current_flags'];pct=s['mc_current_coverage_pct']
        if not (s['mc_current_telemetry_valid']==1 and type(pct) is int and 95<=pct<=100
            and flags&1 and flags&2 and flags&8 and not(flags&(4|16|32))
            and 0<=s['mc_current_age_ms']<750 and 199<=s['mc_current_window_ms']<=220):return False
        for key in ('mc_current_rms_a','mc_current_peak_a','mc_current_instant_a'):
            a=s[key]
            if not isinstance(a,list) or len(a)!=3 or not all(type(v) in (int,float) and math.isfinite(v) for v in a):return False
        return True
    except (KeyError,TypeError,ValueError):return False

trial.ready=ready
trial.active=active
trial.measurement_healthy=measurement_healthy
trial.MEASUREMENT_POLICY='full_valid_rms_min95pct_retained_prestart_sd_sha_verified'

if __name__=='__main__':
    if '--confirm-retained-prestart-sd' not in sys.argv:
        raise SystemExit('Explicit retained-prestart-SD authorization required; no START')
    sys.argv.remove('--confirm-retained-prestart-sd')
    raise SystemExit(trial.main())
