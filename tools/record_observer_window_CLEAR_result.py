"""Record the single CLEAR result without altering previous failed evidence."""
import json
import prepare_observer_current_window as p
from run_foc_boot_capture_trial import decode_boot
def main():
    out=p.OUT/'one_CLEAR_after_RPC_recovery_r1'
    r=json.loads(p.read(out/'report.json'));s=json.loads(p.read(out/'final_status.json'))
    assert r['passed'] and r['CLEAR']==1 and r['START']==r['ARM']==r['RESET']==r['flash']==0
    assert r['UART_latch_cleared'] and r['Break_restored'] and r['MCSDK_faults_cleared']
    assert r['diagnostic']['result_code']==1 and r['diagnostic']['firmware']==p.NEW[1]
    reg=json.loads(p.read(out/'protection_registers_after_CLEAR.json'))
    assert reg['BKE'] and reg['BIE'] and reg['SD_HIGH'] and not reg['MOE']
    prior=json.loads(p.read(p.OUT/'one_CLEAR_idle_r1/report.json'));assert prior['CLEAR']==0
    assert s['algorithm_fast_cycles']==3811 and s['foc_timing_cases']==64 and s['foc_timing_fault']==0
    assert s['foc_runtime']['source']=='OFF_synthetic_CPU_probe' and s['foc_runtime']['observer_steps']==64
    assert s['foc_runtime']['first_fault'] is None and s['foc_runtime']['meter_errors']==0
    old=json.loads(p.read(p.OUT/'installation_verified_r1/report.json'))['after']
    a=decode_boot(old,p.NEW,require_fresh=False);b=decode_boot(s,p.NEW,require_fresh=False)
    source=json.loads(p.read(p.OUT/'source_hashes.json'))
    for rel,h in source.items():assert p.sha(p.OUT/rel)==h,rel
    preserved=json.loads(p.read(out/'preserved_before_sha256.json'))
    for rel,h in preserved.items():assert p.sha(p.ROOT/rel)==h,rel
    summary=dict(passed=True,one_CLEAR_sent=True,first_failed_preflight_CLEAR_sent=False,
        CLEAR=1,START=0,ARM=0,software_MCU_RESET=0,flash=0,
        user_confirmed_Uno_power_cycle=True,owned_HMI_restart=1,router_serial_reopen=1,
        transport_latch_after=0,bad_frame_count_after=0,CRC_error_count_after=0,Uno_UART_hw_errors_after=0,
        current_fault_mask=0,occurred_fault_mask=0,BKE=True,BIE=True,MOE=False,SD='HIGH',
        zero_ready=s['mc_current_zero_ready'],zero_stable_blocks=s['mc_current_zero_stable'],
        OFF_fast_cycles=3811,OFF_budget_cycles=4000,estimate_limit_ms=2,
        source_files_unchanged=len(source),prior_files_verified=len(preserved),
        first_attempt_diagnostic_result='ACK_ACCEPTED',RPC_guard=r['rpc_guard'],
        Linux_boot_changed=a['Linux_boot_id']!=b['Linux_boot_id'],
        native_boot_identity_changed=a['identity']!=b['identity'],
        native_reset_cause_not_proven_by_this_session=True,
        native_old_identity=a['identity'],native_current_identity=b['identity'],
        motor_start_readiness_evaluated=False,J1_must_remain_OFF=True)
    target=out/'acceptance.json';assert not target.exists();p.write(target,json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    m=json.loads(p.read(p.OUT/'manifest.json'))
    m.update(remaining_transport_latch=0,idle_UART_recovered=True,
        latest_no_power_CLEAR_recovery_passed=True,latest_CLEAR_result_code=1,
        strict_installation_idle_gate_passed=m['strict_idle_gate_passed'],
        FOC_start_ready=False,latest_CLEAR_report={target.relative_to(p.OUT).as_posix():p.sha(target)})
    p.write(p.OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
    # Keep the collector's original manifest immutable; seal added passive reads separately.
    p.write(out/'acceptance_files_sha256.json',json.dumps({f.name:p.sha(f) for f in out.iterdir() if f.is_file() and f.name!='acceptance_files_sha256.json'},indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ('passed','CLEAR','transport_latch_after','BKE','BIE','MOE','OFF_fast_cycles','prior_files_verified','native_boot_identity_changed')}))
if __name__=='__main__':main()
