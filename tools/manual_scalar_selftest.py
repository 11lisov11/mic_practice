"""Execute actual manual MCU control and real HTTP routes with mocked hardware."""
import copy
import json
import math
import subprocess
import tempfile
import threading
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from local_stop_fixture_selftest import body
from ipm_break_wifi_selftest import load_module
from prepare_pwm_filter_pair import sha
import uart_recovery_pair_selftest as uart

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=ROOT/'artifacts/live_bench_20261015/manual_scalar_working_pair_r1'

NUCLEO_CASES=r'''
 auto manual=[](unsigned seq,unsigned hz,unsigned rate,uint8_t tag=MSC_TAG_RAMP) {
  auto f=packet(seq,1,3,hz*1000);f[10]=(uint8_t)rate;f[11]=(uint8_t)(rate>>8);
  f[12]=tag;f[13]=MSC_TAG_END;uv3_seal(f.data());return f;
 };
 for(unsigned rate : {10U,100U,500U,5000U}) {
  running();now_ms+=50;feed(manual(5,50,rate));
  check(!uno_link.fault_latched && motor_state==RUN,"manual 50 Hz accepted");
  check(ramp_duration>0 && ramp_duration<=60000,"slow acceleration is segmented within MCSDK timer");
  check(ramp_target<=RPM_2_SPEED_UNIT(3000),"segment does not overshoot 50 Hz");
 }
 running();now_ms+=50;feed(manual(5,50,500));
 check(ramp_duration==9000,"5 to 50 at 5 Hz/s uses nine seconds rather than fixed three");
 now_ms+=50;feed(manual(6,20,100));
 check(!uno_link.fault_latched && ramp_target<RPM_2_SPEED_UNIT(3000),"reduced frequency queues gradual lower segment");
 auto lowered=ramp_target;bus_v=350;uno_link_poll();
 check(uno_link.decel_bus_hold && ramp_target==lowered && ramp_duration==0,"bus rise pauses active down ramp at current field reference");
 now_ms+=50;feed(manual(7,20,100));
 check(uno_link.decel_bus_hold && ramp_target==lowered,"fresh lower commands cannot bypass voltage hold");
 check(peer::g_manual_reference_valid && peer::g_manual_bus_hold,"actual Uno parser receives DC hold and live reference");
 check(std::abs(peer::g_manual_reference_hz-lowered*POLE_PAIR_NUM/(float)SPEED_UNIT)<0.01,"controller field frequency is decoded, not rotor rpm");
 bus_v=345;uno_link_poll();check(uno_link.decel_bus_hold,"bus hold has hysteresis");
 bus_v=340;uno_link_poll();now_ms+=50;feed(manual(8,20,100));
 check(!uno_link.decel_bus_hold && ramp_target<lowered,"automatic descent resumes on bus recovery");
 bus_v=360;uno_link_poll();
 check(uno_link.fault_latched && uno_link.first_reason==UNO_DIAG_BUS && motor_state==IDLE,"continued bus rise stops outputs without resistor");
 running();now_ms+=50;feed(manual(5,50,500,MSC_TAG_COAST));
 now_ms+=50;feed(manual(6,20,100,MSC_TAG_COAST));
 check(uno_link.coast_hold && motor_state==IDLE,"optional coast downshift never brakes");
 now_ms+=50;feed(manual(7,20,100,MSC_TAG_COAST));
 check(motor_state==IDLE,"coast downshift cannot automatically re-enable a spinning rotor");
 now_ms+=50;feed(packet(8));now_ms+=50;feed(manual(9,20,100));
 check(!uno_link.coast_hold && motor_state==RUN,"explicit disabled frame and new start release coast hold");
 for(unsigned rate : {0U,9U,5001U,65535U}) {
  running();now_ms+=50;feed(manual(5,50,rate));
  check(uno_link.fault_latched && motor_state==IDLE,"invalid CRC-valid acceleration cannot energize outputs");
 }
 running();auto bad_manual=manual(5,50,500);bad_manual[13]^=1;uv3_seal(bad_manual.data());now_ms+=50;feed(bad_manual);
 check(uno_link.fault_latched,"bad extension signature rejected");
 running();now_ms+=50;feed(manual(5,50,500));now_ms+=301;uno_link_poll();
 check(uno_link.fault_latched && motor_state==IDLE,"manual parameters preserve 300ms command watchdog");
'''

def compile_run(text,name,out,include):
    cpp=out/(name+'.cpp');cpp.write_text(text);exe=cpp.with_suffix('.exe')
    flags=['g++','-std=c++17','-Ofast','-Wall','-Wextra','-Werror']
    for folder in include:flags+=['-I',str(folder)]
    result=subprocess.run(flags+[str(cpp),'-o',str(exe)],capture_output=True,text=True)
    (out/(name+'_compile.log')).write_text(result.stdout+result.stderr);result.check_returncode()
    result=subprocess.run([str(exe)],capture_output=True,text=True)
    (out/(name+'_run.log')).write_text(result.stdout+result.stderr);result.check_returncode()
    return json.loads(result.stdout)

def uno_program():
    source=(PACKAGE/'UNOQ_MOTOR/UNOQ_MOTOR.ino').read_text()
    assert 'if (manual_watchdog_tick()) return;' in body(source,'control_step')
    funcs='\n'.join(body(source,name) for name in ('manual_set_frequency','manual_command','manual_watchdog_tick'))
    return r'''
#include "manual_scalar_control.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <initializer_list>
#include <strings.h>
uint32_t tick=1000, g_run_limit_ms=0,g_run_deadline_ms=0,g_manual_operator_ms=0;
bool g_pwm_enabled=false,g_start_req=false,g_manual_scalar_mode=false,g_manual_coast_down=false;
bool g_manual_operator_seen=false,g_manual_decreasing=false,g_manual_reference_valid=false;
float g_freq_cmd=0,g_freq_ref=0,g_manual_reference_hz=0,g_last_nonzero_freq=0;
uint16_t g_manual_accel_centi=500,g_manual_decel_centi=100;
enum {STATE_SAFE,STATE_RUN};int g_state=STATE_SAFE;
const float AIR56B2_MAX_ELECTRICAL_FREQ_HZ=50;
unsigned checks=0,estops=0,stops=0;
uint32_t millis(){return tick;}
bool icmp(const char*a,const char*b){return strcasecmp(a,b)==0;}
bool starts_ci(const char*a,const char*b){return strncasecmp(a,b,strlen(b))==0;}
bool parse_single_float_arg(const char*p,float*out){char*end;*out=strtof(p,&end);while(*end==' ')++end;return end!=p && !*end;}
void ext_brake_set(float){}
void hard_stop(bool){++stops;g_pwm_enabled=false;g_state=STATE_SAFE;}
void request_estop_stop(){++estops;g_pwm_enabled=false;g_state=STATE_SAFE;}
void check(bool ok,const char*name){++checks;if(!ok){fprintf(stderr,"FAIL %s\n",name);exit(1);}}
'''+funcs+r'''
int main(){
 check(manual_command("SET RUNMODE MANUAL"),"manual mode while stopped");
 check(!msc_start_allowed(true,0,false),"continuous mode cannot start without operator heartbeat");
 check(manual_command("CONTROL HEARTBEAT"),"operator pulse accepted");
 check(msc_start_allowed(true,0,msc_operator_alive(tick,g_manual_operator_seen,g_manual_operator_ms)),"manual start needs no total-duration timer");
 g_pwm_enabled=true;g_state=STATE_RUN;
 for(tick=1000;tick<100000;tick+=500){manual_command("CONTROL HEARTBEAT");check(!manual_watchdog_tick(),"manual run survives former 15s/ARM time limit with operator control");}
 tick=g_manual_operator_ms+2999;check(!manual_watchdog_tick(),"fresh operator remains active");
 tick=g_manual_operator_ms+3000;check(manual_watchdog_tick() && estops==1 && !g_pwm_enabled,"HMI crash/client disappearance independently stops MCU");
 for(const char*bad : {"SET ACCEL nan","SET ACCEL inf","SET ACCEL -1","SET ACCEL 0","SET ACCEL 51","SET DECEL 5.1","SET ACCEL 2 junk"})check(!manual_command(bad),"nonfinite/range/extra argument rejected under Ofast");
 for(const char*good : {"SET ACCEL 0.1","SET ACCEL 50","SET DECEL 0.1","SET DECEL 5"})check(manual_command(good),"online ramp settings accepted");
 for(float f : {0.0f,0.1f,5.0f,20.0f,50.0f})check(manual_set_frequency(f) && g_freq_cmd==f,"whole 0..50 setpoint range");
 check(!manual_set_frequency(50.1f) && !manual_set_frequency(-1),"out-of-range target rejected");
 check(!manual_set_frequency(NAN) && !manual_set_frequency(INFINITY),"nonfinite target rejected under Ofast");
 g_pwm_enabled=true;g_state=STATE_RUN;g_freq_cmd=g_freq_ref=50;
 check(manual_set_frequency(20) && g_pwm_enabled && g_manual_decreasing,"default lower target remains running and uses deceleration");
 check(!manual_command("SET RUNMODE BOUNDED") && !manual_command("SET DOWNMODE COAST"),"run mode cannot change underneath active outputs");
 g_pwm_enabled=false;g_state=STATE_SAFE;check(manual_command("SET DOWNMODE COAST"),"optional coast mode configurable stopped");
 g_pwm_enabled=true;g_state=STATE_RUN;g_freq_cmd=g_freq_ref=50;
 check(manual_set_frequency(20) && !g_pwm_enabled && stops==1 && g_freq_cmd==20,"optional coast retains new target but never auto-starts");
 check(!msc_start_allowed(false,0,true) && msc_start_allowed(false,15000,false),"bounded profile retains backup-timer requirement");
 check(msc_operator_alive(20,true,0xFFFFFFF0U),"operator watchdog handles millisecond wrap");
 int16_t next=0;
 for(unsigned rate : {10U,50U,100U,500U,5000U}) for(int target=1;target<=500;++target){
  int current=0;unsigned steps=0;
  while(current<target){auto duration=msc_segment(current,target,rate,10,1,&next);check(next>current && next<=target && duration>0 && duration<=60000,"slow ramp reaches exact target with bounded segment");current=next;check(++steps<1000,"segmented ramp progresses");}
 }
 printf("{\"pass\":true,\"assertions\":%u,\"hardware_commands\":0}\n",checks);
}
'''

def http_tests(out):
    mod=load_module(PACKAGE/'web_hmi/server.py');cases=0
    def check(condition,name):
        nonlocal cases
        assert condition,name;cases+=1
    # Actual new MessagePack array mapping, including controller-reference source.
    values=[0]*99
    values[3]=12.0;values[15]=50.0;values[26]=20
    pair=json.loads((PACKAGE/'manifest.json').read_text())['pair']
    values[70]=pair[0];values[75]=3;values[78]=pair[1]
    values[91:]=[1,1,5.0,1.0,0,23.4,1,1]
    bridge=mod.RpcBridge.__new__(mod.RpcBridge)
    bridge._call=lambda *args,**kwargs:[1,0,None,values]
    bridge._serial_text=None
    decoded_ok,decoded,error=bridge.get()
    check(decoded_ok and decoded['freq']==23.4 and decoded['freq_cmd']==50.0 and decoded['local_ramp_reference_hz']==12.0,'actual new RPC array uses controller reference without overwriting target')
    check(decoded['mc_decel_bus_hold']==1 and decoded['accel_hz_per_s']==5.0,'new RPC array carries hold and ramp settings')
    values[26]=500
    check(bridge.get()[1]['freq']==12.0,'stale controller reference is not substituted as fresh')
    values[26]=20;values[78]=2026101414
    check(not mod.manual_scalar_supported(bridge.get()[1]),'mixed RPC identities cannot activate manual controls')
    old=ROOT/'artifacts/live_bench_20261014/snapshot_stop_sync_hil_r1'
    original=(old/'vbus_recalibration_preparation/original_vbus_calibration.json').read_bytes()
    store=mod.VbusCalibrationStore(str(old/'vbus_recalibration_preparation/original_vbus_calibration.json'))
    status=json.loads((old/'working_bus_on_1791997952551152700/first_status.json').read_text())
    status.update(fw_build=pair[0],mc_fw_build=pair[1],bp_fw_build=pair[1],
        manual_scalar_capable=1,manual_run_mode=0,accel_hz_per_s=5.,decel_hz_per_s=1.,downmode_coast=0,
        state='SAFE',state_code=0,pwm=0,estop=0,bp_fault=0,bp_status=1,bp_softstart_ready=1,
        bp_age_ms=20,bp_rsp_age_ms=20,mc_age_ms=20,mc_rsp_age_ms=20,bp_vbus_age_ms=20,bp_temp_age_ms=20,
        vdc=324.,bp_vdc=324.,bp_vbus_raw=3240,freq_cmd=5.,freq=0.,link=True)
    def canonical(data):
        for k,v in list(data.items()):
            if k.startswith('bp_'):data['mc_'+k[3:]]=v
        return mod.with_motor_controller_aliases(data)
    status=canonical(status)
    check(store.is_valid(status),'preserved calibration accepted only on audited matching pair')
    for changes in ({'fw_build':2026101415},{'mc_fw_build':2026101414},{'manual_scalar_capable':0}):
        check(not mod.manual_scalar_supported(dict(status,**changes)),'unknown/mixed pair cannot select continuous mode')
    class RPC:
        def __init__(self):self.data=copy.deepcopy(status);self.commands=[];self.heartbeat_ok=True
        def get(self):return True,canonical(copy.deepcopy(self.data)),''
        def cmd(self,command):
            self.commands.append(command)
            if command=='CONTROL HEARTBEAT' and not self.heartbeat_ok:return False,'offline injected RPC failure'
            if command=='START':self.data.update(state='VF_RUN',state_code=1,pwm=1,bp_status=0x23,freq=self.data['freq_cmd'])
            elif command in ('STOP','ESTOP'):self.data.update(state='SAFE',state_code=0,pwm=0,bp_status=1,freq=0.)
            elif command.startswith('SET FREQ '):self.data['freq_cmd']=float(command.split()[-1])
            return True,''
    rpc=RPC();opener=build_opener(ProxyHandler({}))
    with tempfile.TemporaryDirectory() as temporary:
        tokenfile=Path(temporary)/'token';tokenfile.write_text('offline-manual-test-key')
        cfg=mod.HvArmConfig(enabled=True,min_vdc=250,max_vdc=360)
        app=mod.AppState(rpc,mod.LogStore(65536,None,65536),0,
            command_guard=mod.CommandGuardConfig(max_vdc=400,allow_hv=True,local_bench_gate=True),
            hv_arm=mod.HvArmState(cfg),start_runlimit_sec=15,
            control_access=mod.ControlAccessConfig(str(tokenfile)),vbus_calibration=store)
        http=mod.ThreadingHTTPServer(('127.0.0.1',0),mod.Handler);http.app=app
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        def post(path,data,authenticated=True):
            headers={'Content-Type':'application/json'}
            if authenticated:headers['X-UNOQ-Control-Token']='offline-manual-test-key'
            request=Request(f'http://127.0.0.1:{http.server_port}'+path,json.dumps(data).encode(),headers,method='POST')
            try:
                with opener.open(request,timeout=5) as response:return response.status,json.load(response)
            except HTTPError as error:return error.code,json.load(error)
        try:
            check(post('/api/start-sequence',{'manual':True},False)[0]==401 and not rpc.commands,'authentication cannot be skipped')
            check(post('/api/start-sequence',{'manual':True})[0]==409 and 'START' not in rpc.commands,'ARM still required')
            check(post('/api/hv-arm',{'action':'arm','confirm':cfg.confirm})[0]==200,'ordinary ARM')
            for invalid in ({'manual':'true'},{'manual':True,'runlimit_s':3}):
                check(post('/api/start-sequence',invalid)[0]==409,'invalid/mixed profile rejected')
            check(post('/api/start-sequence',{'manual':True})[0]==200,'manual HTTP START')
            check('SET RUNMODE MANUAL' in rpc.commands and 'SET RUNLIMIT 0.000' in rpc.commands,'MCU continuous mode configured explicitly')
            check('CONTROL HEARTBEAT' in rpc.commands,'MCU watchdog primed before START')
            app.hv_arm._expires_at=mod._now_ts()-1000
            check(app.hv_arm.snapshot()['hmi_hv_armed']==1 and not app.hv_arm.take_expired_session_action(),'active manual session exceeds former total timer')
            check(app.hv_arm.runtime_monitor_required() and app.hv_arm.snapshot()['hmi_run_continuous']==1,'continuous session still requires health monitoring')
            count=rpc.commands.count('CONTROL HEARTBEAT')
            check(post('/api/operator-heartbeat',{})[0]==200 and rpc.commands.count('CONTROL HEARTBEAT')==count+1,'real authenticated HTTP heartbeat reaches MCU')
            check(post('/api/operator-heartbeat',{},False)[0]==401 and rpc.commands.count('CONTROL HEARTBEAT')==count+1,'unauthenticated browser cannot feed MCU watchdog')
            for freq in (50,20,5):check(post('/api/cmd',{'cmd':f'SET FREQ {freq}'})[0]==200 and rpc.data['freq_cmd']==freq,'online full-range up/down target')
            rpc.heartbeat_ok=False
            check(post('/api/operator-heartbeat',{})[0]==503,'lost MCU heartbeat is reported, not silently renewed')
            rpc.heartbeat_ok=True
            check(post('/api/stop-sequence',{'emergency':False})[0]==200 and rpc.data['pwm']==0,'ordinary STOP confirms outputs off')
            check(not app._manual_mcu_watchdog,'STOP stops forwarding operator pulses')
            check(not app.hv_arm.command_allowed(rpc.get()[1])[0],'STOP revokes armed session')
            check(post('/api/hv-arm',{'action':'arm','confirm':cfg.confirm})[0]==200,'next ARM remains ordinary repeatable')
            check(post('/api/start-sequence',{'runlimit_s':3})[0]==200,'bounded mode still works')
            check('SET RUNMODE BOUNDED' in rpc.commands and 'SET RUNLIMIT 3.000' in rpc.commands,'bounded backup timer retained')
            check(post('/api/stop-sequence',{})[0]==200,'bounded STOP')
            check('CLEAR' not in rpc.commands,'no automatic fault acknowledgement')
        finally:http.shutdown();http.server_close();thread.join(timeout=4)
    check((old/'vbus_recalibration_preparation/original_vbus_calibration.json').read_bytes()==original,'original calibration bytes untouched')
    return {'pass':True,'cases':cases,'hardware_commands':0,'scope':'Real HTTP handlers and manual-session expiry/watchdog forwarding, mocked MCU and motor'}

def main():
    attempt=1
    while (PACKAGE/f'tests_manual_r{attempt}').exists():attempt+=1
    out=PACKAGE/f'tests_manual_r{attempt}';out.mkdir(exist_ok=False)
    program=uart.build_program(PACKAGE)
    marker=' std::printf("{\\"pass\\":true'
    assert marker in program
    program=program.replace(marker,NUCLEO_CASES+'\n'+marker,1)
    nuc=compile_run(program,'actual_nucleo_manual',out,[PACKAGE/'nucleo/Inc',PACKAGE/'UNOQ_MOTOR'])
    uno=compile_run(uno_program(),'actual_uno_manual',out,[PACKAGE/'UNOQ_MOTOR'])
    http=http_tests(out)
    report={'pass':True,'hardware_commands':0,'hardware_validated':False,'nucleo':nuc,'uno':uno,'http':http,
        'scope':'Actual Nucleo parser/command/feedback to actual Uno parser; actual Uno manual command/watchdog functions; real HMI HTTP. HAL/MCSDK/motor mocked.',
        'nucleo_sha256':sha(PACKAGE/'nucleo/Src/main.c'),'uno_sha256':sha(PACKAGE/'UNOQ_MOTOR/UNOQ_MOTOR.ino'),
        'hmi_sha256':sha(PACKAGE/'web_hmi/server.py'),'header_sha256':sha(PACKAGE/'nucleo/Inc/manual_scalar_control.h')}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    mf=json.loads((PACKAGE/'manifest.json').read_text());mf['manual_selftest_report']=str((out/'report.json').relative_to(PACKAGE))
    (PACKAGE/'manifest.json').write_text(json.dumps(mf,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
