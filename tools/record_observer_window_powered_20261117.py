"""Archive powered GET-only preflight, retain the explicit protection blockers."""
import json
import prepare_observer_current_window as p
def main():
    out=p.OUT/'powered_before_FOC_20261117_r1'
    r=json.loads(p.read(out/'report.json'));s=json.loads(p.read(out/'final_status.json'))['data']
    assert r['START']==r['CLEAR']==r['ARM']==r['RESET']==r['flash']==r['SWD']==0
    assert r['failed_checks']==['no_fault_latches','SD_break_IRQ_ready']
    assert r['checks']['UART_RPC_clean'] and r['checks']['autonull_ready'] and r['checks']['CPU64_cases']
    prior=p.OUT/'autonomous_before_FOC_20261117_r1'
    old=(prior/'SD_first_boot.bin').read_bytes()
    snap=json.loads(p.read(out/'SD_snapshots.json'))['data'];now=bytes.fromhex(snap['mc_break_wave_hex'])
    assert now==old,'First SD capture changed'
    (out/'SD_first_boot_unchanged.bin').write_bytes(now)
    for folder,name in [(prior,'extended_saved_files_sha256.json'),(p.OUT/'one_CLEAR_after_RPC_recovery_r1','acceptance_files_sha256.json')]:
        for rel,h in json.loads(p.read(folder/name)).items():assert p.sha(folder/rel)==h,rel
    result=dict(START=0,CLEAR=0,ARM=0,RESET=0,flash=0,
        vdc_range_V=r['vdc_range'],SD_live='HIGH',Break_IRQ_ready=False,
        active_fault_mask=s['mc_fault_current_mask'],saved_fault_mask=s['mc_fault_occurred_mask'],
        active_MC_UNDER_VOLT_still_reported=True,
        UART_RPC_clean=True,autonull_ready=True,fast_cycles=3811,fast_budget_cycles=4000,estimate_limit_ms=2,
        original_SD_capture_unchanged=True,original_SD_SHA256=p.sha(out/'SD_first_boot_unchanged.bin'),
        ADC_observer_recorders_unoccupied=True,motor_start_ready=False,
        algorithm_selected=s['algorithm_selected'],algorithm_requested=s['algorithm_requested'],
        needs_explicit_standard_CLEAR_and_recheck=True,
        no_automatic_CLEAR_or_START_authorized=True,old_capture_files_verified=r['preserved_files_verified'])
    p.write(out/'readiness_axes.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    p.write(out/'extended_saved_files_sha256.json',json.dumps({f.name:p.sha(f) for f in out.iterdir() if f.is_file() and f.name!='extended_saved_files_sha256.json'},indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()
