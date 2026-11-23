"""Archive GET-only autonomous axes and the first boot Break; no device access."""
import json
import prepare_observer_current_window as p
def main():
    out=p.OUT/'autonomous_before_FOC_20261117_r1'
    report=json.loads(p.read(out/'report.json'))
    s=json.loads(p.read(out/'final_status.json'))['data']
    assert report['START']==report['CLEAR']==report['ARM']==report['RESET']==report['flash']==report['SWD']==0
    assert report['samples']==20 and not report['passed']
    failed=[k for k,v in report['checks'].items() if not v]
    assert failed==['SD_break_IRQ_ready'],failed
    trace=json.loads(p.read(out/'SD_trace.json'))['data']
    snap=json.loads(p.read(out/'SD_snapshots.json'))['data']
    wave=bytes.fromhex(snap['mc_break_wave_hex']);assert len(wave)==320
    (out/'SD_first_boot.bin').write_bytes(wave)
    assert trace['post_complete'] and not any(trace[k] for k in ('timeout','dma_error','sampling_overrun','run_overflow'))
    pulse=trace['channels']['pa6_bkin']['selected_pulse'];assert pulse['pulse_complete']
    first=next(x for x in snap['mc_break_snapshots'] if x['kind']=='first_since_boot')
    assert first['captured'] and first['event']['moe_at_irq'] is False
    assert not first['event']['during_start_request_window']
    result=dict(autonomous_link_passed=True,autonull_passed=True,CPU_passed=True,
        full_protection_readiness=False,motor_start_ready=False,
        START=0,CLEAR=0,ARM=0,RESET=0,flash=0,
        observation_samples=20,quiet_window_seconds=report['rpc_guard']['quiet_window_seconds'],
        fast_cycles=report['fast_kernel_cycles'],fast_budget_cycles=4000,estimate_limit_ms=2,
        new_UART_RPC_errors=0,zero_ready=1,zero_stable_blocks=3,
        ADC_and_observer_recorders_unoccupied=True,
        SD_live='HIGH',Break_IRQ_enabled=False,first_Break_tick_ms=trace['event_tick_ms'],
        first_SD_low_us=pulse['width_us'],first_SD_pulse_complete=True,first_SD_MOE=False,
        first_SD_SHA256=p.sha(out/'SD_first_boot.bin'),
        active_mask=s['mc_fault_current_mask'],saved_mask=s['mc_fault_occurred_mask'],
        current_bus_V=s['vdc'],J1_OFF=True,
        TP23_PA4_not_electrically_comparable='External TP23->PA4 jumper was removed earlier; PA4 HIGH is not proof of TP23 HIGH',
        no_fault_clear_authorized_this_turn=True,old_capture_files_verified=report['preserved_files_verified'])
    target=out/'readiness_axes.json';assert not target.exists();p.write(target,json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    p.write(out/'extended_saved_files_sha256.json',json.dumps({f.name:p.sha(f) for f in out.iterdir() if f.is_file() and f.name!='extended_saved_files_sha256.json'},indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()
