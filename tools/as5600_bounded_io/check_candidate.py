"""Fault injection, actual deadline-branch execution and late HTTP replay."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import prepare_as5600_bounded_io as p
import prepare_current_shunt_monitor as u

def main():
    out=p.OUT;sk=out/'UNOQ_MOTOR';checks=[]
    compiler=shutil.which('g++');assert compiler
    exe=out/'build/uno/poll_selftest.exe'
    subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(sk),str(p.RES/'selftest.cpp'),'-o',str(exe)],check=True)
    result=subprocess.run([str(exe)],check=True,capture_output=True,text=True)
    checks.append(result.stdout.strip())
    before=u.read(p.BASE/'UNOQ_MOTOR/UNOQ_MOTOR.ino');after=u.read(sk/'UNOQ_MOTOR.ino')
    start=after.index('  if (g_pwm_enabled && g_run_deadline_ms != 0U')
    end=after.index('\n  if (g_toggle_req)',start)
    branch=after[start:end]
    test='''#include "timed_run.h"
#include "mcsdk_supervisory.h"
#include <cassert>
TimedRun g_timed_run;bool g_pwm_enabled=true,g_estop_latched=false;unsigned stops=0;uint32_t g_run_deadline_ms=0;
void request_normal_stop(){++stops;g_pwm_enabled=false;g_timed_run.finish(g_timed_run.stop_ms,TimedRun::STOP);}
void tick(uint32_t now_ms){
'''+branch+'''
}
int main(){for(uint32_t start:{0U,UINT32_MAX-4999U,UINT32_MAX-2000U}){
 for(unsigned web_delay:{0U,5000U,20000U}){
  (void)web_delay;stops=0;g_pwm_enabled=true;g_estop_latched=false;
  g_timed_run.start(start,5000);g_run_deadline_ms=unoq_bounded_run_deadline(start,5000,0,true);
  tick(start+4999);assert(stops==0);
  tick(start+5001);assert(stops==1&&!g_pwm_enabled&&!g_estop_latched&&g_timed_run.reason==1&&g_timed_run.elapsed(0)==5001);
  tick(start+20000);assert(stops==1);
 }
 auto d=unoq_bounded_run_deadline(start,5000,0,true);
 assert(unoq_bounded_run_deadline(start+1000,5000,d,true)==d);
} }
'''
    test=test.replace('#include <cassert>','#include <cassert>\n#include <initializer_list>')
    unit=out/'build/uno/deadline_branch.cpp';unit.write_text(test)
    exe2=out/'build/uno/deadline_branch.exe'
    subprocess.run([compiler,'-std=c++17','-Wall','-Wextra','-Werror','-I',str(sk),str(unit),'-o',str(exe2)],check=True)
    subprocess.run([str(exe2)],check=True)
    checks.append('Actual MCU deadline branch: no HTTP dependence, wrap, no extension, normal STOP once')
    # Compare all pre-existing protection code before the changed finite-limit clause.
    a=before[before.index('static void control_step() {'):before.index('  if (g_pwm_enabled && g_run_deadline_ms != 0U')]
    b=after[after.index('static void control_step() {'):start]
    assert a==b
    checks.append('All protection code preceding deadline unchanged')
    for f in (p.BASE/'UNOQ_MOTOR').iterdir():
        if f.is_file() and f.name not in ('UNOQ_MOTOR.ino','as5600_teacher.h','as5600_teacher.cpp'):
            assert f.read_bytes()==(sk/f.name).read_bytes(),f.name
    assert before[before.index('static void hard_stop(bool clear_cmd, bool force_link) {'):before.index('static bool manual_set_frequency')].replace(
        '  const bool outputs_were_active = g_pwm_enabled || g_pwm_outputs_active || g_state != STATE_SAFE;',
        '  const bool outputs_were_active = g_pwm_enabled || g_pwm_outputs_active || g_state != STATE_SAFE;\n  g_timed_run.finish(millis(),TimedRun::STOP);') in after
    checks.append('UART, ADC, SD, physical fault and hard STOP bodies retained')
    cmsis=Path('C:/Users/USER/AppData/Local/Arduino15/packages/arduino/hardware/zephyr/0.90.0/variants/arduino_uno_q_stm32u585xx/llext-edk/include/modules/hal/stm32/stm32cube/stm32u5xx/soc/stm32u585xx.h').read_text()
    for name,bit in dict(TXIS=1,RXNE=2,NACKF=4,STOPF=5,TC=6,BERR=8,ARLO=9,OVR=10,BUSY=15).items():
        assert re.search(r'#define I2C_ISR_'+name+r'_Pos\s+\('+str(bit)+r'U\)',cmsis),name
    checks.append('Polling ISR masks match pinned STM32U585 CMSIS definitions')
    spec=importlib.util.spec_from_file_location('bounded_hmi',out/'web_hmi/server.py')
    h=importlib.util.module_from_spec(spec);sys.modules[spec.name]=h;spec.loader.exec_module(h)
    recorded=json.loads((p.BASE/'legacy_powered_5hz_r1/report.json').read_text())
    s=copy.deepcopy(recorded['before']);s.update(fw_build=2026102516,run_id=8,run_start_ms=0xffffff00,
        run_stop_ms=(0xffffff00+5000)&0xffffffff,run_limit_ms=5000,run_elapsed_ms=5000,run_reason=1)
    assert h.bounded_run_complete(s,dict(run_id=7),5)
    for key,value in dict(run_id=7,run_reason=2,run_limit_ms=7000,run_elapsed_ms=4999,
                          pwm=1,estop=1,mc_fault=1,mc_fault_current_mask=4,mc_transport_fault=4,mc_fw_build=0).items():
        assert not h.bounded_run_complete(dict(s,**{key:value}),dict(run_id=7),5),key
    # Replay real start function with a completed run delivered instead of VF_RUN.
    class Rpc:
        def __init__(self):self.commands=[]
        def cmd(self,c):self.commands.append(c);return True,None
        def get(self):return True,s,None
    class Arm:
        cfg=h.HvArmConfig(enabled=True)
        def command_allowed(self,data):return True,None
        def set_manual_session(self,x):pass
        def disarm(self):self.disarmed=True
    class Logs:
        def add(self,line):pass
    class Calibration:
        def is_valid(self,status):return True
    class App:
        rpc=Rpc();hv_arm=Arm();logs=Logs();vbus_calibration=Calibration();command_guard=h.CommandGuardConfig(max_vdc=20);_manual_start_requested=False
        def maybe_log_fault_diagnostics(self,x):pass
        def stop_sequence(self,**kw):raise AssertionError('No emergency escalation after verified normal completion')
    app=App();initial=dict(recorded['before'],fw_build=2026102516,run_id=7)
    okay,message,status=h.App._start_without_precharge(app,initial,1,.01,5) if hasattr(h,'App') else (None,None,None)
    if okay is None:
        cls=next(v for v in vars(h).values() if isinstance(v,type) and hasattr(v,'_start_without_precharge'))
        okay,message,status=cls._start_without_precharge(app,initial,1,.01,5)
    assert okay and status['pwm']==0 and app.rpc.commands.count('START')==1 and app.hv_arm.disarmed
    checks.append('Actual HMI start with late completed5s response: no restart or emergency escalation')
    bridge=object.__new__(h.RpcBridge);observed=[]
    bridge._call=lambda method,args,**kw:observed.append((args[0],kw['retries'])) or [0,0,None,True]
    bridge._serial_text=None
    for cmd in ('START','CLEAR','STOP'):assert bridge.cmd(cmd)[0]
    assert observed==[('START',0),('CLEAR',0),('STOP',2)]
    checks.append('No RPC replay of START/CLEAR on lost reply')
    line='DATA state=SAFE mode=VF pwm=0 '+ ' '.join(f'run_{f}={i+1}' for i,f in enumerate((*p.RUN_FIELDS,'elapsed_ms')))
    parsed=h.RpcBridge._parse_status_string(line)
    assert all(parsed[f'run_{f}']==i+1 for i,f in enumerate((*p.RUN_FIELDS,'elapsed_ms')))
    target=[x['status'] for x in recorded['samples'] if x['status'].get('mc_current_telemetry_valid')==1][-1]
    old=h.with_shunt_currents(copy.deepcopy(target));new=h.with_shunt_currents(dict(copy.deepcopy(target),fw_build=2026102516))
    assert new['mc_current_rms_a']==old['mc_current_rms_a'] and new['mc_current_coverage_pct']==100
    assert not h.manual_scalar_supported(dict(new,fw_build=2026102599))
    stored=dict(fw_build=2026102515,mc_fw_build=2026102510,rpc_schema_version=3,mc_capabilities=1,mc_mcsdk_telemetry=1)
    assert h._vbus_calibration_identity_matches(stored,dict(stored,fw_build=2026102516))
    assert not h._vbus_calibration_identity_matches(stored,dict(stored,fw_build=2026102599))
    checks.append('Real recorded ADC/zero telemetry decoded for new pair; unknown pair rejected')
    # Replay observed long driver duration: new reader reports deadline, not valid data.
    active=[x['status'] for x in recorded['samples'] if x['status']['pwm']==1]
    replay={'recorded_native_max_us':max(x['enc_diag_us'] for x in active),
            'recorded_sensor_errors':max(x['enc_errors'] for x in active),
            'physical_cause_proven':False,'hardware_glitch_reproduction':False}
    (out/'recorded_replay.json').write_text(json.dumps(replay,indent=2)+'\n')
    report=dict(passed=True,hardware_commands=0,hardware_validated=False,checks=checks,
        scheduler_delay_limitation='3ms deadline is checked while scheduled; this is not a hard wall-clock guarantee under arbitrary preemption',
        stop_scope='MCU dispatch timestamps; actual Nucleo PWM-off latency must be verified after installation')
    (out/'offline-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
