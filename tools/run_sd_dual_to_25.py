"""One staged dual-SD diagnostic run, at most 25 Hz; never runs on import.

The first capture must be empty, SD HIGH and BKIN interrupt enabled. Retained
running Break evidence is never cleared here. One known startup DC-undervoltage
acknowledgement is inherited; any occupied capture prevents acknowledgement.
"""
import json
from pathlib import Path
import sys
import run_uart_tx_dma_to_50 as tested
import prepare_sd_dual_capture as package

tested.common.PAIR=package.NEW
runner=tested.runner
runner.PLAN=((5,12),(10,10),(15,10),(20,10),(25,10))
runner.MAX_RUN_S=60
runner.PROFILE='dual-sd-5-to-25-steps-of-5'

def selftest():
    root=package.ROOT/'artifacts/live_bench_20261021/sd_dual_retry_preparation_r1'
    actual=json.loads((root/'before_status.json').read_text(encoding='utf-8'))
    checks=[]
    def check(value,name):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    # Synthetic fixtures only. No fixture is ever submitted to a controller.
    clean=dict(actual)
    clean.update(bp_fault=0,mc_fault=0,mc_fault_current_mask=0,mc_fault_occurred_mask=0,
                 estop=0,mc_break_wave_hex='-',mc_break_snapshots=[
                     {'available':True,'captured':False,'reason':'no_recorded_break'},
                     {'available':True,'captured':False,'reason':'no_recorded_break'}])
    clean['mc_sd_live']=dict(actual['mc_sd_live'],level='HIGH',break_irq_enabled=True,
                            capture_running=True,first_record_ready=False)
    check(runner.ready(clean) and runner.capture_free(clean),'fresh exact pair can enter run preparation')
    check(not runner.ready(actual) and not tested.startup_ack_allowed(actual),
          'actual occupied 18-ms capture is rejected without CLEAR or START')
    uv=dict(clean,mc_fault=5,bp_fault=5,mc_fault_reason=8,
            mc_fault_current_mask=4,mc_fault_occurred_mask=4)
    check(tested.startup_ack_allowed(uv),'only known startup UV can be acknowledged once')
    for key,value in [('mc_fault_current_mask',0x400),('mc_fault_occurred_mask',0x404),
                      ('mc_uart_error_flags',2),('mc_age_ms',300),('vdc',200),
                      ('mc_fw_build',2026102002),('pwm',1),('estop',1)]:
        bad=dict(uv,**{key:value})
        check(not tested.startup_ack_allowed(bad),'startup acknowledgement rejects '+key)
    for key,value in [('level','LOW'),('break_irq_enabled',False),('capture_running',False),
                      ('first_record_ready',True),('config_ok',False)]:
        bad=dict(clean,mc_sd_live=dict(clean['mc_sd_live'],**{key:value}))
        check(not runner.ready(bad),'run preparation rejects SD '+key)
    check(runner.PLAN[-1][0]==25 and max(x[0] for x in runner.PLAN)==25 and runner.MAX_RUN_S==60,
          'diagnostic range and deadline bounded')
    result=dict(passed=True,synthetic_fixtures=True,checks=checks,hardware_commands=0,
                motor_commands=0,reset_commands=0,clear_commands=0,
                requested_targets_hz=[x[0] for x in runner.PLAN],host_deadline_s=60,
                operator_watchdog_s=3,actual_preparation_ready=False)
    (root/'runner_selftest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('passed','requested_targets_hz','host_deadline_s','hardware_commands','actual_preparation_ready')}))

if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:selftest()
    else:raise SystemExit(runner.main())
