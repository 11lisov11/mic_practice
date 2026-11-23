"""Pure host policy regression; no network, motor commands or firmware changes."""
import copy
import json
from pathlib import Path
import run_current_adc_window_diagnostic as d

ROOT=Path(__file__).resolve().parents[1]
def main():
    base=ROOT/'artifacts/live_bench_20261024/current_zero_noise_r1/peak_trial_30_to_50_r1/report.json'
    r=json.loads(base.read_text(encoding='utf-8'))
    s=next(copy.deepcopy(x['status']) for x in r['samples'] if x['status'].get('pwm')==1
        and x['status'].get('mc_current_telemetry_valid')==1 and x['status'].get('mc_current_window_ms',0)>=199)
    s.update(fw_build=d.PAIR[0],mc_fw_build=d.PAIR[1])
    target=s['freq_cmd'];assert d.measurement_healthy(s) and d.trial.active(s,target)
    assert d.trial.PROFILES['30-to-50']==((30,13),(35,8),(40,8),(45,8),(50,8))
    assert not d.ready(s)
    partial=dict(s,mc_current_flags=(s['mc_current_flags']|64)&~2,
        mc_current_telemetry_valid=0,mc_current_coverage_pct=89,
        mc_current_rms_a=None,mc_current_peak_a=None,mc_current_instant_a=None)
    assert d.measurement_healthy(partial)
    assert d.current_at_target(partial,partial['mc_frequency_reference_hz'])
    checks=5
    for change in ({'mc_current_coverage_pct':74},{'mc_current_coverage_pct':101},
        {'mc_current_flags':partial['mc_current_flags']|32},
        {'mc_current_flags':partial['mc_current_flags']|4},
        {'mc_current_flags':partial['mc_current_flags']|16},
        {'mc_current_flags':partial['mc_current_flags']|2},
        {'mc_current_flags':partial['mc_current_flags']&~8},
        {'mc_current_age_ms':750},{'mc_current_detail_age_ms':1500},
        {'mc_current_quality_age_ms':1500},{'mc_current_window_ms':0},
        {'mc_current_window_ms':221},{'mc_current_bad':1},
        {'mc_current_rms_a':[0,0,0]},{'mc_current_peak_a':[0,0,0]},
        {'mc_current_instant_a':[0,0,0]}):
        assert not d.measurement_healthy(dict(partial,**change)),change;checks+=1
    for change in ({'mc_fault':1},{'bp_fault':1},{'mc_fault_current_mask':1},
        {'mc_fault_occurred_mask':1},{'estop':1},{'mc_bad_cnt':1},
        {'mc_uart_error_flags':1},{'bp_transport_fault':1},
        {'hmi_hv_armed':0},{'fw_build':0},{'mc_age_ms':300}):
        assert not d.trial.active(dict(partial,**change),target),change;checks+=1
    low=copy.deepcopy(partial);low['mc_sd_live']['level']='LOW'
    assert not d.trial.active(low,target);checks+=1
    for change in ({'mc_current_rms_a':None},{'mc_current_rms_a':[float('nan'),0,0]},
        {'mc_current_flags':s['mc_current_flags']&~2},{'mc_current_coverage_pct':94}):
        assert not d.measurement_healthy(dict(s,**change)),change;checks+=1
    print(json.dumps(dict(passed=True,checks=checks,hardware_commands=0,
        invalid_rms_remains_none=True,adc_clip_and_stale_rejected=True,
        physical_and_transport_gates_preserved=True)))
if __name__=='__main__':main()
