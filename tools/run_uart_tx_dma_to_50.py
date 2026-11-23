"""Same bounded staged run on exact TX-DMA pair, with fresh SD preconditions."""
import run_fast_bkin_short_scalar as common
import time
common.PAIR=(2026101813,2026101812)
import run_fast_bkin_to_50 as runner
runner.ERROR_KEYS=runner.ERROR_KEYS+('mc_uart_reject_bad_pages',)
original_ready=runner.ready

def ready(s):
    sd=s.get('mc_sd_live',{})
    return (original_ready(s) and s.get('hmi_manual_scalar_supported')==1
            and s.get('manual_scalar_capable')==1
            and sd.get('available') is True and sd.get('level')=='HIGH'
            and sd.get('config_ok') is True and sd.get('break_irq_enabled') is True
            and sd.get('capture_running') is True and sd.get('first_record_ready') is False)

runner.ready=ready

def startup_ack_allowed(s):
    return (common.off(s) and runner.transport_clean(s) and common.capture_free(s)
        and s.get('mc_fault')==5 and s.get('bp_fault')==5 and s.get('estop')==0
        and s.get('mc_fault_reason')==8 and s.get('mc_fault_current_mask') in (0,4)
        and s.get('mc_fault_occurred_mask')==4 and s.get('mc_last_bad_reason')==0
        and s.get('mc_last_uart_error_flags')==0 and s.get('mc_uart_reject_hex')=='-'
        and s.get('mc_sd_live',{}).get('available') is True
        and s['mc_sd_live'].get('level')=='HIGH' and s['mc_sd_live'].get('config_ok') is True
        and s['mc_sd_live'].get('break_irq_enabled') is True and s['mc_sd_live'].get('capture_running') is True)

def prepare_startup(h,s,save,report):
    if ready(s):return s
    if not startup_ack_allowed(s):return s
    # Only an archived mains-off undervoltage after independently confirmed
    # power preparation and recovered >=250-V/soft-start telemetry. Never DP,
    # UART, an occupied capture or a running drive; one acknowledgement only.
    save('before_startup_uv_ack.json',s)
    h.command('CLEAR');report['clear_commands']=1
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        s=h.status()
        if ready(s):save('after_startup_uv_ack.json',s);return s
        time.sleep(.2)
    raise RuntimeError('Single known startup undervoltage acknowledgement did not clear; no retry or START')

runner.PREPARE_STARTUP=prepare_startup

if __name__=='__main__':raise SystemExit(runner.main())
