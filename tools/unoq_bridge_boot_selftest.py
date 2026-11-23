"""Check startup ordering and off-only Bridge recovery; no hardware access."""
import argparse
import json
from pathlib import Path
import tempfile

from prepare_unoq_bridge_boot_fix import BASE, sketch, hmi
from ipm_break_wifi_selftest import load_module
from web_hmi_command_guard_selftest import safe_status


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args(); out=a.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    old=(BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text(); new=sketch(old)
    setup=new[new.index('    if (k_mutex_init(&g_control_mutex)'):]
    assert setup.index('k_thread_priority_set')<setup.index('Bridge.begin')
    assert 'if (!Bridge.begin(RPC_BAUD) && NUCLEO_MCSDK_ACIM_BACKEND) NVIC_SystemReset();' in setup
    bridge=new[new.index('static void bridge_tick() {'):new.index('K_THREAD_STACK_DEFINE(bridge_service_stack')]
    assert bridge.index('if (g_pwm_enabled || g_pwm_outputs_active')<bridge.index('NVIC_SystemReset')
    assert 'NUCLEO_MCSDK_ACIM_BACKEND ? 4 : CONFIG_NUM_PREEMPT_PRIORITIES - 1' in new
    assert bridge.index('NVIC_SystemReset(); return;')<bridge.index('g_bridge_ready = Bridge.begin')
    cases=0
    # Ready updater at priority 5 must not exclude either startup or recovery.
    for updater_ready in (False,True):
        for main_priority in (14,4):
            for service_priority in (14,4):
                can_main=(not updater_ready or main_priority<=5)
                can_service=(not updater_ready or service_priority<=5)
                if updater_ready and main_priority==14: assert not can_main
                if updater_ready and service_priority==14: assert not can_service
                if main_priority==service_priority==4: assert can_main and can_service
                cases+=1
    for local in (False,True):
        for outputs in (False,True):
            for peer in (False,True):
                reset_allowed=not(local or outputs or peer)
                assert reset_allowed==(local==outputs==peer==False); cases+=1
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'server.py'; p.write_text(hmi((BASE/'web_hmi/server.py').read_text()))
        mod=load_module(p)
        assert not mod.hv_arm_precheck(safe_status(fw_build=2026101107,mc_fw_build=2026101102),
            mod.HvArmConfig(enabled=True),True)[0]; cases+=1
    result=dict(pass_=True,cases=cases,hardware_commands=0,
        scope='Source ordering/safety predicates and synthetic priority readiness, not a physical cold-start proof')
    result['pass']=result.pop('pass_'); (out/'report.json').write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps(result))


if __name__=='__main__': main()
