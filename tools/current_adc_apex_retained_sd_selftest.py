"""Pure policy tests: archived SD admission never bypasses a live fault."""
import copy
import json
from pathlib import Path
import run_current_adc_apex_retained_sd_trial as d

ROOT=Path(__file__).resolve().parents[1]
def main():
    s=copy.deepcopy(d.ACK['final_status']);assert d.ready(s);checks=1
    changes=({'pwm':1},{'hmi_hv_armed':1},{'estop':1},{'mc_fault':5},{'bp_fault':5},
        {'mc_fault_current_mask':1024},{'mc_fault_occurred_mask':1024},
        {'mc_uart_error_flags':2},{'mc_bad_cnt':1},{'mc_age_ms':300},
        {'mc_current_zero_ready':0},{'mc_break_wave_hex':'-'},{'fw_build':0})
    for change in changes:assert not d.ready(dict(s,**change)),change;checks+=1
    for key,value in (('level','LOW'),('break_irq_enabled',False),('config_ok',False),('first_record_ready',False)):
        bad=copy.deepcopy(s);bad['mc_sd_live'][key]=value;assert not d.ready(bad);checks+=1
    for which,key,value in (('first_since_boot','moe_at_irq',True),('first_since_boot','during_start_request_window',True)):
        bad=copy.deepcopy(s);next(x for x in bad['mc_break_snapshots'] if x['kind']==which)['event'][key]=value
        assert not d.ready(bad);checks+=1
    bad=copy.deepcopy(s);next(x for x in bad['mc_break_snapshots'] if x['kind']=='first_start_window')['captured']=True
    assert not d.ready(bad);checks+=1
    old=ROOT/'artifacts/live_bench_20261024/current_adc_window_fix_r1/peak_trial_30_to_50_r1/report.json'
    r=json.loads(old.read_text(encoding='utf-8'))
    active=next(copy.deepcopy(x['status']) for x in r['samples'] if x['status'].get('pwm')==1 and x['status'].get('mc_current_telemetry_valid')==1 and x['status'].get('mc_current_window_ms',0)>=199)
    active.update(fw_build=2026102509,mc_fw_build=2026102510,mc_break_wave_hex=s['mc_break_wave_hex'])
    assert d.active(active,active['freq_cmd']) and d.measurement_healthy(active);checks+=1
    for change in ({'mc_current_coverage_pct':94},{'mc_current_telemetry_valid':0},
        {'mc_current_flags':active['mc_current_flags']|32},{'mc_current_flags':active['mc_current_flags']|4},
        {'mc_current_age_ms':750},{'mc_current_rms_a':None},{'mc_current_rms_a':[float('nan'),0,0]}):
        assert not d.measurement_healthy(dict(active,**change)),change;checks+=1
    for change in ({'mc_fault':5},{'mc_fault_occurred_mask':1024},{'bp_transport_fault':4},{'mc_break_wave_hex':'-'}):
        assert not d.active(dict(active,**change),active['freq_cmd']),change;checks+=1
    assert d.trial.PROFILES['30-to-50']==((30,13),(35,8),(40,8),(45,8),(50,8));checks+=1
    print(json.dumps(dict(passed=True,checks=checks,hardware_commands=0,
        retained_record_hash_required=True,live_fault_and_sd_gates_preserved=True,rms_min95pct=True)))
if __name__=='__main__':main()
