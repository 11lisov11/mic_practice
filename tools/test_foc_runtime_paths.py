"""Execute the actual dispatcher, RX slice and diagnostic scheduling off-target."""
import json,re,subprocess
import prepare_foc_runtime_fix as p
from audit_production_pwm_filters import function
from test_foc_runtime_fix import compile_run

def main():
 out=p.OUT/'verification'
 dispatch=function(p.read(p.OUT/'nucleo/Src/mc_tasks.c'),'TSK_HighFrequencyTask')
 pre=r'''
#include <cassert>
#include <cstdint>
#define __weak
enum{M1=0,MC_NO_ERROR=0};
struct Timer{};struct PWM{Timer*TIMx;};static Timer timer;static PWM pwm={&timer};static PWM*pwmHandle[]={&pwm};
struct VF{float fFlux_Freq_Hz;};static VF vf={5};static VF*pACIM_VF[]={&vf};
static int enabled,selected,angles,scalar,native_calls,profiles,faults,ret;
static int LL_TIM_IsEnabledAllOutputs(Timer*){return enabled;}
static void ma_native_profile_tick(){++profiles;}
static void ACIM_VF_CalcAngle(VF*){++angles;}
static uint16_t ACIM_VF_Controller(VF*){++scalar;return ret;}
static unsigned ma_native_selected(){return selected;}
static uint16_t ma_native_fast(float f){assert(f==5);++native_calls;return ret;}
static void PWM_SwitchOffPWM(PWM*){enabled=0;}
static int Mci[1];static void MCI_FaultProcessing(int*,int f,int){assert(f==ret);++faults;}
static unsigned GLOBAL_TIMESTAMP;struct Log{unsigned Mark;};static Log MCPA_UART_A={};
static void MCPA_dataLog(Log*){}
'''
 checks=r'''
int main(){
 enabled=0;selected=1;TSK_HighFrequencyTask();assert(profiles==1&&!angles&&!scalar&&!native_calls);
 enabled=1;selected=1;TSK_HighFrequencyTask();assert(angles==1&&scalar==1&&!native_calls);
 selected=2;TSK_HighFrequencyTask();assert(angles==1&&scalar==1&&native_calls==1);
 selected=3;TSK_HighFrequencyTask();assert(angles==1&&native_calls==2);
 ret=128;TSK_HighFrequencyTask();assert(!enabled&&faults==1);
}
'''
 compile_run(out,'dispatch',pre+dispatch+checks)
 main=p.read(p.OUT/'nucleo/Src/main.c')
 poll=function(main,'uno_link_poll')
 match=re.search(r'  uint8_t byte, flags;.*?^  }',poll,re.S|re.M);assert match
 rx=match[0]
 pre=r'''
#include <cassert>
#include <cstdint>
enum{UV3_FRAME=43};static unsigned available=100,consumed;static bool abort_rx;
static bool uno_rx_pop(uint8_t*b,uint8_t*f){if(!available)return false;--available;*b=0;*f=0;return true;}
static bool uno_abort_pending_rx_fault(){return abort_rx;}
static void uno_consume_sample(uint8_t,uint8_t){++consumed;}
'''
 checks='void run_slice(){\n'+rx+'\n}\nint main(){run_slice();assert(consumed==43&&available==57);run_slice();assert(consumed==86&&available==14);run_slice();assert(consumed==100&&!available);available=20;abort_rx=true;run_slice();assert(consumed==100);}'
 compile_run(out,'rx_slice',pre+checks)
 reply=function(main,'uno_send_reply')
 begin=reply.index('  if (tx_status == HAL_OK) {');end=reply.index('  if (tx_status != HAL_OK)')
 diagnostic=reply[begin:end]
 pre=r'''
#include <cassert>
#include <cstdint>
enum{HAL_OK=0};static int tx_status;static uint32_t now_ms;static int enabled,service,live,bulk;
static int timer;static int*TIM1=&timer;static int LL_TIM_IsEnabledAllOutputs(int*){return enabled;}
static void ma_native_service(){++service;}
static void mic_send_research_page(uint32_t){++live;}
static void mic_send_current_page(uint32_t){++live;}
static void mic_send_break_page(uint32_t){++bulk;}
static void mic_send_peak_page(uint32_t){++bulk;}
static void mic_send_noise_page(uint32_t){++bulk;}
static void mic_send_identification(uint32_t){++bulk;}
'''
 checks='void reply(){\n'+diagnostic+'\n}\nint main(){enabled=1;reply();assert(service==3&&live==2&&!bulk);enabled=0;reply();assert(service==6&&live==4&&bulk==4);tx_status=1;reply();assert(service==6&&live==4&&bulk==4);}'
 compile_run(out,'diagnostics',pre+checks)
 # Native protection dispatch and SDK scalar implementation are untouched.
 vf='nucleo/MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/acim_vf_control.c'
 assert p.read(p.OUT/vf)==p.read(p.BASE/vf)
 assert 'fmod((double)' in p.read(p.OUT/vf)
 assert '    ma_native_service();\n    uno_link_poll();' in main
 # Decode the actual HMI function without importing/starting the web service.
 server=p.read(p.OUT/'web_hmi/server.py')
 start=server.index('def foc_runtime_status(kv):');stop=server.index('\ndef sd_live_status',start)
 scope={};exec(server[start:stop],scope);decode=scope['foc_runtime_status']
 w=[0]*28;w[:7]=[148155,120000,28155,14,148155,120000,28155]
 w[14:21]=[4,3,1000000,990000,650000,820000,900000]
 kv={'foc_runtime_valid':'1','foc_runtime_flags':'1',**{'foc_runtime_w'+str(i):str(v) for i,v in enumerate(w)}}
 d=decode(kv)['foc_runtime'];assert d['available'] and d['observer_wall_us']==871.5
 assert d['first_fault']['reason_code']==4 and d['first_fault']['estimate_age_us']>2000
 bad=dict(kv);bad['foc_runtime_w1']='148156';assert not decode(bad)['foc_runtime']['available']
 bad=dict(kv);bad['foc_runtime_w0']='-1';assert not decode(bad)['foc_runtime']['available']
 assert not decode({})['foc_runtime']['available']
 r=subprocess.run(['C:/Program Files/nodejs/node.exe','--check',str(p.OUT/'web_hmi/static/app.js')],capture_output=True,text=True)
 p.write(out/'javascript.log',r.stdout+r.stderr);r.check_returncode();compile(server,'server.py','exec')
 report=dict(passed=True,hardware_commands=0,scalar_angle_called_only_for_VF=True,
  MOE_off_skips_dispatch=True,native_fault_still_switches_PWM_off=True,
  UART_slice_43bytes_and_abort_checked=True,bulk_diagnostics_deferred_until_OFF=True,
  live_control_and_current_telemetry_retained=True,
  HMI_cpu_irq_and_frozen_fault_decode_checked=True,Python_and_JS_checked=True)
 p.write(out/'path_tests.json',json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
