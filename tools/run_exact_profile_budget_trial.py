"""One authorized1503/1504 FOC5Hz5s trial using unchanged bounded supervision."""
import copy,json,sys
from pathlib import Path
import prepare_exact_profile_budget as p
import run_observer_input_epoch_trial as driver

# Imported collectors configure old packages on import; bind ALL identities
# after those imports. No safety predicate, deadline or runtime body is edited.
driver.package=p
driver.trial.PAIR=p.NEW
driver.boot.package=p
driver.boot.trial=driver.trial
driver.capture.package=p
driver.capture.base=driver.boot


def package_check():
    m=json.loads(p.read(p.OUT/'manifest.json'))
    assert m['installed'] and m['OFF_CPU_qualified']
    assert (m['CPU_probe_budget_cycles'],m['estimate_limit_ms'],m['trip_A'],m['ADC_guard_ticks'])==(4000,2,1.35,2048)
    assert m['fast_budget_cycles']==5312 and m['runlimit_ms']==5000
    for file in ('source_hashes.json','preserved_capture_hashes.json'):
        root=p.OUT if file=='source_hashes.json' else p.ROOT
        for rel,digest in json.loads(p.read(p.OUT/file)).items():assert p.sha(root/rel)==digest,rel
    for rel,digest in m['artifacts'].items():assert p.sha(p.OUT/rel)==digest,rel


def offline_check():
    target=p.OUT/'powered_trial_preparation_r1';target.mkdir(exist_ok=False)
    s=json.loads(p.read(p.OUT/'powered_preflight_FOC_r1/final_status.json'))['data']
    trial=driver.trial
    assert trial.PAIR==p.NEW and driver.boot.package is p and driver.capture.package is p
    assert trial.off(s) and trial.link_power(s) and trial.off_timing_ready(s)
    driver.boot.decode_boot(s,p.NEW)
    assert not trial.healthy(s)  # Recorded UNDER_VOLT/disabled Break IRQ blocks START.
    good=copy.deepcopy(s)
    good.update(algorithm_selected=2,algorithm_requested=2,mc_fault=0,bp_fault=0,
                mc_fault_current_mask=0,mc_fault_occurred_mask=0,estop=0,algorithm_fault=0)
    good['mc_sd_live']['break_irq_enabled']=True
    assert trial.profile(good) and trial.healthy(good) and trial.off_timing_ready(good)
    for key,value in [('mc_fault_current_mask',4),('mc_fault_occurred_mask',1024),
        ('mc_transport_fault',7),('mc_current_zero_ready',0),('algorithm_fault',3),
        ('mc_bad_cnt',1),('mc_last_uart_error_flags',2),('mc_age_ms',301),('vdc',0)]:
        bad=copy.deepcopy(good);bad[key]=value
        assert not trial.healthy(bad),key
    for cycles in (4001,5313):assert not trial.off_timing_ready(dict(good,algorithm_fast_cycles=cycles))
    for changes in ({'level':'LOW'},{'break_irq_enabled':False},{'config_ok':False}):
        bad=copy.deepcopy(good);bad['mc_sd_live'].update(changes);assert not trial.healthy(bad)
    result=dict(passed=True,network_requests=0,motor_commands=0,pair=list(p.NEW),
        saved_preclear_blocks_START=True,negative_guards_retained=True,
        runtime_source_SHA256=p.sha(p.ROOT/'tools/run_observer_input_epoch_runtime.py'),
        wrapper_source_SHA256=p.sha(p.ROOT/'tools/run_observer_input_epoch_trial.py'),
        CPU_budget=4000,estimate_limit_ms=2,trip_A=1.35,ADC_guard_ticks=2048)
    p.write(target/'report.json',json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


def main():
    package_check()
    if '--offline-check-only' in sys.argv:
        offline_check();return 0
    preparation=json.loads(p.read(p.OUT/'powered_trial_preparation_r1/report.json'))
    assert preparation['passed']
    assert preparation['runtime_source_SHA256']==p.sha(p.ROOT/'tools/run_observer_input_epoch_runtime.py')
    assert preparation['wrapper_source_SHA256']==p.sha(p.ROOT/'tools/run_observer_input_epoch_trial.py')
    out=Path(sys.argv[sys.argv.index('--outdir')+1]).resolve()
    assert p.OUT in out.parents and not out.exists()
    return driver.main()


if __name__=='__main__':raise SystemExit(main())
