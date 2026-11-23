"""One staged 5..50-Hz run on the exact clean-confirmation pair, when prepared.

No run on import. Existing SD, health, watchdog and STOP guards are preserved.
"""
import json
import sys
import prepare_uart_clean_confirm as package
import run_uart_tx_dma_to_50 as tested

tested.common.PAIR=package.NEW
runner=tested.runner
runner.PROFILE='dual-sd-uart-clean-confirm-5-to-50'

def selftest():
    p=package.ROOT/'artifacts/live_bench_20261021/sd_dual_after_reset_r1/final_status.json'
    s=json.loads(p.read_text(encoding='utf-8'));s=s.get('data',s)
    s.update(fw_build=package.NEW[0],mc_fw_build=package.NEW[1])
    assert runner.ready(s) and runner.capture_free(s)
    tests=1
    for key,value in [('mc_transport_fault',5),('bp_transport_fault',5),('mc_uart_error_flags',4),
                      ('mc_bad_integrity',1),('mc_bad_sequence',1),('mc_fw_build',package.OLD[1]),
                      ('mc_fault',1),('estop',1),('pwm',1),('vdc',200),('mc_age_ms',300)]:
        bad=dict(s,**{key:value})
        assert not runner.ready(bad),key
        assert not tested.startup_ack_allowed(bad),key
        tests+=1
    for key,value in [('level','LOW'),('break_irq_enabled',False),('capture_running',False),
                      ('first_record_ready',True),('config_ok',False)]:
        bad=dict(s,mc_sd_live=dict(s['mc_sd_live'],**{key:value}))
        assert not runner.ready(bad),key;tests+=1
    assert [x[0] for x in runner.PLAN]==list(range(5,51,5)) and runner.MAX_RUN_S==100
    r=dict(passed=True,checks=tests,synthetic_fixtures=True,hardware_commands=0,motor_commands=0,
           requested_targets_hz=[x[0] for x in runner.PLAN],host_deadline_s=runner.MAX_RUN_S,
           operator_watchdog_s=3,installed=False,run_performed=False)
    (package.OUT/'runner_selftest.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(r))

if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:selftest()
    else:raise SystemExit(runner.main())
