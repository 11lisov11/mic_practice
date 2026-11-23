"""Offline local-stop interleavings and non-actuating preparation lifecycle."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from ipm_break_wifi_selftest import load_module
from nucleo_button_restart_audit import function
from prepare_nucleo_local_stop import PWM
from unoq_boot_trial_selftest import proof, status


PREAMBLE = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
struct TIM_TypeDef { uint32_t BDTR = 0; };
TIM_TypeDef timer;
#define TIM1 (&timer)
enum { GPIO_PIN_SET=1, IDLE=0, RUN=1, STOPPING=2, MC_NO_FAULTS=0,
       Start_Stop_GPIO_Port=0, Start_Stop_Pin=13, LL_EXTI_LINE_13=13,
       LL_TIM_OSSI_ENABLE=1 };
bool held=false, pending=false, irq_deferred=false;
uint32_t mask=0;
unsigned injection=0, calls=0, starts=0, checks=0, stops=0;
int state=IDLE;
unsigned current_faults=0, occurred_faults=0;
uint8_t bMCBootCompleted=1;
void UI_HandleStartStopButton_cb();
void press() {
 held=true; pending=true;
 if (mask) irq_deferred=true;
 else { pending=false; UI_HandleStartStopButton_cb(); }
}
void boundary() { if (injection && ++calls == injection) press(); }
int HAL_GPIO_ReadPin(int,int) { boundary(); return held ? GPIO_PIN_SET : 0; }
bool LL_EXTI_IsActiveFlag_0_31(int) { boundary(); return pending; }
uint32_t __get_PRIMASK() { return mask; }
void __disable_irq() { mask=1; }
void __set_PRIMASK(uint32_t m) {
 mask=m;
 if (!mask && irq_deferred) {
   irq_deferred=false; pending=false; UI_HandleStartStopButton_cb();
 }
}
void LL_TIM_DisableAllOutputs(TIM_TypeDef *t) { t->BDTR &= ~0x8000U; }
void LL_TIM_EnableAllOutputs(TIM_TypeDef *t) { boundary(); t->BDTR |= 0x8000U; }
bool LL_TIM_IsEnabledAllOutputs(TIM_TypeDef *t) { return bool(t->BDTR & 0x8000U); }
void LL_TIM_ClearFlag_UPDATE(TIM_TypeDef*) {}
void LL_TIM_EnableIT_UPDATE(TIM_TypeDef*) {}
int MC_GetSTMStateMotor1() { return state; }
unsigned MC_GetCurrentFaultsMotor1() { return current_faults; }
unsigned MC_GetOccurredFaultsMotor1() { return occurred_faults; }
bool MC_StopMotor1() { ++stops; if (state != IDLE) state=STOPPING; return state!=IDLE; }
bool MC_StartMotor1() { ++starts; return true; }
struct PWM_Handle_t { TIM_TypeDef *TIMx; };
void check(bool v) { ++checks; assert(v); }
'''

CASES = r'''
void reset() {
 held=pending=irq_deferred=false; mask=0; injection=calls=starts=stops=0;
 state=IDLE; current_faults=occurred_faults=0;
 mic_local_stop_latched=0; timer.BDTR=0;
 bMCBootCompleted=1;
}
int main() {
 PWM_Handle_t pwm{TIM1};
 reset(); bMCBootCompleted=0; press();
 check(mic_local_stop_latched==1 && stops==0);
 held=false; PWM_SwitchOnPWM(&pwm); check(!LL_TIM_IsEnabledAllOutputs(TIM1));
 reset(); PWM_SwitchOnPWM(&pwm); check(LL_TIM_IsEnabledAllOutputs(TIM1));
 state=RUN; press(); check(!LL_TIM_IsEnabledAllOutputs(TIM1));
 check(mic_local_stop_latched==1 && state==STOPPING);
 held=false; state=IDLE;
 for (unsigned i=0;i<1000;++i) {
   if (!mic_local_stop_blocked()) MC_StartMotor1();
   PWM_SwitchOnPWM(&pwm);
   check(!LL_TIM_IsEnabledAllOutputs(TIM1));
 }
 check(starts==0); check(mic_local_stop_latched==1);
 check(mic_local_stop_clear()); check(!LL_TIM_IsEnabledAllOutputs(TIM1));
 if (!mic_local_stop_blocked()) MC_StartMotor1();
 PWM_SwitchOnPWM(&pwm); check(starts==1 && LL_TIM_IsEnabledAllOutputs(TIM1));
 // Pending start publication cannot re-enable MOE after a serviced button IRQ.
 reset(); MC_StartMotor1(); press(); held=false;
 PWM_SwitchOnPWM(&pwm); check(!LL_TIM_IsEnabledAllOutputs(TIM1));
 // Inject edges before/during the atomic output enable operation.
 for (unsigned n=1;n<=3;++n) {
   reset(); injection=n; PWM_SwitchOnPWM(&pwm);
   check(held); check(mic_local_stop_latched==1);
   check(!LL_TIM_IsEnabledAllOutputs(TIM1)); check(mask==0);
 }
 reset(); mic_local_stop_latched=1; held=true;
 check(!mic_local_stop_clear()); check(mic_local_stop_latched==1);
 held=false; pending=true; check(!mic_local_stop_clear());
 pending=false; state=STOPPING; check(!mic_local_stop_clear());
 state=IDLE; timer.BDTR=0x8000; check(!mic_local_stop_clear());
 timer.BDTR=0; current_faults=4; check(!mic_local_stop_clear());
 current_faults=0; occurred_faults=4; check(!mic_local_stop_clear());
 occurred_faults=0; check(mic_local_stop_clear());
 for (unsigned n=1;n<=2;++n) {
   reset(); mic_local_stop_latched=1; injection=n;
   check(!mic_local_stop_clear()); check(mic_local_stop_latched==1);
 }
 reset(); mask=1; PWM_SwitchOnPWM(&pwm); check(mask==1);
 press(); check(mic_local_stop_blocked()); PWM_SwitchOnPWM(&pwm);
 check(!LL_TIM_IsEnabledAllOutputs(TIM1)); __set_PRIMASK(0);
 std::printf("checks=%u\n",checks);
}
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--hmi',type=Path,required=True)
    p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args(); out=a.outdir.resolve(); out.mkdir(parents=True,exist_ok=False)
    project=a.candidate/'nucleo'
    main_text=(project/'Src/main.c').read_text()
    assert 'GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;' in main_text
    assert 'PC13.GPIO_ModeDefaultEXTI=GPIO_MODE_IT_RISING' in next(project.glob('*.ioc')).read_text()
    # Extract the actual candidate bodies, rather than testing a second guard model.
    names=('mic_local_button_pending','mic_local_stop_blocked','UI_HandleStartStopButton_cb',
           'mic_local_stop_enable_outputs','mic_local_stop_clear')
    import re
    def body(name):
        match=re.search(r'(?:static\s+)?(?:bool|void)\s+'+name+r'\([^;]*?\)\s*\{',main_text)
        if not match: raise RuntimeError(name)
        end=match.end();depth=1
        while depth:
            depth+=(main_text[end]=='{')-(main_text[end]=='}');end+=1
        return main_text[match.start():end]
    core='volatile uint32_t mic_local_stop_latched;\n'+'\n'.join(body(n) for n in names)
    publication=function((project/PWM).read_text(),'PWM_SwitchOnPWM')
    program=PREAMBLE+core+'\n'+publication+CASES
    compiler=shutil.which('g++')
    if not compiler: raise RuntimeError('g++ required')
    cpp=out/'local_stop.cpp';cpp.write_text(program)
    exe=cpp.with_suffix('.exe')
    subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)],check=True,capture_output=True,text=True)
    run=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
    mutations={
        'no_output_guard':('mic_local_stop_enable_outputs(pHandle->TIMx)', 'LL_TIM_EnableAllOutputs(pHandle->TIMx)'),
        'no_sticky_stop':('mic_local_stop_latched = 1U;\n  LL_TIM_DisableAllOutputs(TIM1);', 'mic_local_stop_latched = 0U;\n  LL_TIM_DisableAllOutputs(TIM1);'),
        'held_clear_allowed':('const bool allowed = !mic_local_button_pending() &&', 'const bool allowed = true &&'),
        'boot_stop_call_unguarded':('if (bMCBootCompleted != 0U) (void)MC_StopMotor1();', '(void)MC_StopMotor1();'),
        'wrong_mb1367_button_polarity':('HAL_GPIO_ReadPin(Start_Stop_GPIO_Port, Start_Stop_Pin) == GPIO_PIN_SET ||',
                                       'HAL_GPIO_ReadPin(Start_Stop_GPIO_Port, Start_Stop_Pin) != GPIO_PIN_SET ||'),
    }
    detected=[]
    for name,(before,after) in mutations.items():
        if program.count(before)!=1: raise RuntimeError('Mutation anchor: '+name)
        unit=out/(name+'.cpp');unit.write_text(program.replace(before,after))
        binary=unit.with_suffix('.exe')
        subprocess.run([compiler,'-std=c++17',str(unit),'-o',str(binary)],check=True,capture_output=True,text=True)
        result=subprocess.run([str(binary)],capture_output=True,text=True)
        if result.returncode==0: raise AssertionError('Surviving mutation '+name)
        detected.append(name)
    checks=0
    def check(value):
        nonlocal checks
        checks+=1; assert value
    mod=load_module(a.hmi)
    s={**status(),'fw_build':mod.BOOT_TRIAL_PAIR[0],'mc_fw_build':mod.BOOT_TRIAL_PAIR[1]}
    g=mod.PoweredTrialGate(1,pair=mod.BOOT_TRIAL_PAIR,wait_without_deadline=True)
    check(g.expires_at is None)
    check(g.snapshot()['hmi_powered_trial_wait_limited']==0)
    check(g.snapshot()['hmi_powered_trial_remaining_s'] is None)
    g.created-=86400
    check(not g.ready(s,True)[0])
    g.begin=time.monotonic()-31;g.last_seen=time.monotonic();g.first_good=0;g.last_good=100;g.samples=20
    check(g.ready(s,True)[0])
    check((g.max_run_s,g.stop_after_s,g.max_freq_hz)==(3,3,5))
    check(not g.ready({**s,'bp_age_ms':300},True)[0])
    check(g.begin is None)
    g.begin=time.monotonic()-31;g.last_seen=time.monotonic();g.first_good=0;g.last_good=100;g.samples=20
    check(not g.ready(s,False)[0])
    old=mod.PoweredTrialGate(1,pair=mod.BOOT_TRIAL_PAIR)
    old.expires_at=time.monotonic()-1
    check(not old.ready(s,True)[0])
    for pair,profile,policy in ((mod.UART_V3_TRIAL_PAIR,'short',True),
                              (mod.BOOT_TRIAL_PAIR,'coast30',True),
                              (mod.BOOT_TRIAL_PAIR,'short',1)):
        try: mod.PoweredTrialGate(1,pair=pair,profile=profile,wait_without_deadline=policy)
        except ValueError: check(True)
        else: check(False)
    valid=proof(mod)
    valid.update(scope='local_stop_with_hardware_pwm_validation',
                 nucleo_local_stop_source_audit_pass=True,local_stop_hardware_validated=True,
                 new_pair_active_pwm_measured=True,physical_idle_registers_current=True)
    check(mod.validate_powered_trial_qualification(valid)[0])
    for key in ('local_stop_hardware_validated','new_pair_active_pwm_measured',
                'physical_idle_registers_current','nucleo_local_stop_source_audit_pass'):
        check(not mod.validate_powered_trial_qualification({**valid,key:False})[0])
    check(not mod.validate_powered_trial_qualification({**valid,'issued_at':time.time()-1000,'expires_at':time.time()-400})[0])
    for key,value in (('bp_fault',5),('bp_transport_fault',1),('vdc',400),('freq_cmd',6)):
        check(not g.ready({**s,key:value},True)[0])
    g.consume();check(not g.ready(s,True)[0])
    try:g.consume()
    except RuntimeError:check(True)
    else:check(False)
    check(not mod.hv_arm_precheck({**s,'mc_fw_build':2026101201},mod.HvArmConfig(enabled=True),True)[0])
    check(not mod.hv_arm_precheck({**s,'bp_status':0x80},mod.HvArmConfig(enabled=True),True)[0])
    check('wait_without_deadline=tuple(proof["pair"]) == BOOT_TRIAL_PAIR' in a.hmi.read_text())
    restarted=mod.PoweredTrialGate(1,pair=mod.BOOT_TRIAL_PAIR,wait_without_deadline=True)
    restarted.observe(s,True)
    check(not restarted.ready({**s,'bp_good':99},True)[0])
    check(restarted.invalidated_reason=='prepared controller restarted')
    check(not restarted.ready(s,True)[0])
    changed=mod.PoweredTrialGate(1,pair=mod.BOOT_TRIAL_PAIR,wait_without_deadline=True)
    check(not changed.ready({**s,'mc_fw_build':2026101102},True)[0])
    check(changed.invalidated_reason=='prepared peer identity changed')
    check(not changed.ready(s,True)[0])
    class Rpc:
        def __init__(self,data):self.data=data;self.commands=[]
        def get(self):return True,self.data,None
        def cmd(self,command):self.commands.append(command);return True,None
    class Logs:
        def add(self,line):pass
    with tempfile.TemporaryDirectory() as directory:
        cal_path=Path(directory)/'cal.json'
        record=dict(schema=mod.VbusCalibrationStore.SCHEMA,
                    identity=dict(fw_build=2026092901,mc_fw_build=2026100601,
                                  rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1),
                    points={'zero':{'meter_vdc':0,'mc_vdc_mean':0},
                            'high':{'meter_vdc':322.7,'mc_vdc_mean':325}})
        record['integrity_sha256']=mod.VbusCalibrationStore._digest(record)
        cal_path.write_text(json.dumps(record));original=cal_path.read_bytes()
        cal=mod.VbusCalibrationStore(str(cal_path))
        for volts,expected in ((0,True),(9,True),(10.01,False),(320,False)):
            rpc=Rpc(dict(s,vdc=volts,bp_vdc=volts,bp_vbus_raw=round(volts*10),rpc_schema_version=3))
            app=mod.AppState(rpc,Logs(),status_log_interval=1,
                hv_arm=mod.HvArmState(mod.HvArmConfig(enabled=True)),vbus_calibration=cal,
                control_access=mod.ControlAccessConfig(token_file='test-only'))
            ok,_=app.prepare_powered_trial(valid,'PREPARE UARTV3 TRIAL 3S')
            check(ok is expected);check(not rpc.commands)
            if expected:
                check(app.hv_arm.cfg.trial_gate.expires_at is None)
                check(app.hv_arm.cfg.ttl_sec<=10)
                check(app.hv_arm.cfg.trial_gate.max_run_s==3)
        check(cal_path.read_bytes()==original)
    report=dict(pass_=True,hardware_commands=0,hardware_validated=False,
                local_stop_output=run.stdout.strip(),mutations_detected=detected,hmi_checks=checks,
                active_limits_unchanged=True,
                limitations=['HAL/MCSDK calls mocked; not a physical interrupt latency measurement',
                             'Candidate image not installed; physical PWM and button tests still required'])
    report['pass']=report.pop('pass_')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
