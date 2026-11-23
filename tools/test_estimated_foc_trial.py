"""Test actual native adapter, calculated-profile gate and native five-second stop."""
import ast,hashlib,json,shutil,subprocess
import prepare_estimated_foc_trial as p
from audit_production_pwm_filters import function

def main():
 out=p.OUT/'verification';out.mkdir(exist_ok=True)
 tree=ast.parse(p.read(p.ROOT/'tools/test_multi_algorithm.py'))
 method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='test_native_adapter_and_wire_actual_c')
 pre=ast.literal_eval(next(n for n in method.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='pre' for t in n.targets)).value)
 pre=pre.replace('return 320;','return fake_bus;').replace('static uint16_t VBS_GetAvBusVoltage_V',
  'static uint16_t fake_bus=0;\nstatic uint16_t VBS_GetAvBusVoltage_V')
 pre+='''
#include "identify_core.h"
#include "identify_wire.h"
#include "foc_experiment.h"
#include <initializer_list>
static int PWM_ParamsM1,off_calls;
static void PWM_SwitchOffPWM(int*){timer.BDTR=0;++off_calls;}
static uint32_t ticks;static uint32_t host_profile_clock(){return ticks+=100;}
enum{TIM1_UP_TIM16_IRQn=25};static unsigned kicks;
static void NVIC_SetPendingIRQ(int);
'''
 source=p.read(p.OUT/'nucleo/Src/multi_native.c')
 for name in ('ma_native_profile_tick','fe_profile_tick','fe_profile_service'):
  f=function(source,name);source=source.replace(f,f.replace('DWT->CYCCNT','host_profile_clock()'))
 source='\n'.join(line for line in source.splitlines() if not line.startswith(('#include','#pragma')))
 checks=r'''
static void NVIC_SetPendingIRQ(int irq){assert(irq==25);++kicks;ma_native_profile_tick();}
static void config(uint8_t*p,unsigned op,unsigned index,uint32_t value){
 memset(p,0,UV3_FRAME);p[4]=8;p[6]=(uint8_t)op;p[7]=(uint8_t)index;
 memcpy(p+8,&value,4);p[12]=1;p[13]=0xA6;
}
int main(){
 const float edge[]={0.f,-0.f,1.f,-1.f,1.e-30f,-1.e-30f,1.e30f,-1.e30f,INFINITY,-INFINITY,NAN};
 for(float a:edge)for(float b:edge){
  float lo=std::fmin(a,b),hi=std::fmax(a,b);
  assert(std::isnan(lo)?std::isnan(ma_min2(a,b)):lo==ma_min2(a,b));
  assert(std::isnan(hi)?std::isnan(ma_max2(a,b)):hi==ma_max2(a,b));
 }
 for(float magnitude:{.0001001f,.01f,.25f,1.f,2.f})for(int i=0;i<1440;i++){
  float t=i*.00436332313f,a=magnitude*cosf(t),b=magnitude*sinf(t);
  float norm=hypotf(a,b),angle=atan2f(b,a);
  assert(fabsf(cosf(angle)-a/norm)<2.e-6f&&fabsf(sinf(angle)-b/norm)<2.e-6f);
 }
 assert(profile_ready&&qualification==128&&selected==MA_VF&&fe_model_exact(&model));
 assert(!fe_profile_allowed(MA_FOC)&&!ma_native_request(MA_FOC));
 sample.zero=1;fake_bus=320;fe_profile_service();assert(!fe_started);
 fake_bus=0;timer.BDTR=1;fe_profile_service();assert(!fe_started);timer.BDTR=0;
 for(unsigned i=0;i<3000&&!(fe_flags()&FE_READY);i++){
  ma_native_service();ma_native_profile_tick();
 }
 assert(id_profile_cycles==100&&fe_complete&&!fe_fault&&fe_case==64);
 assert(kicks>0);
 assert(fe_fast_cycles==100&&fe_observer_cycles==100&&timer.CCR1==100&&timer.CCR2==200&&timer.CCR3==300);
 assert(off_calls==0&&!id_state.ready&&!id_state.accepted);
 assert(ma_native_request(MA_FOC)&&!ma_native_request(MA_ADAPTIVE));
 assert(ma_native_reference_allowed(MA_FOC,5000)&&!ma_native_reference_allowed(MA_FOC,5001));
 assert(!ma_native_reference_allowed(MA_ADAPTIVE,5000));
 for(unsigned flags=0;flags<8;flags++)for(unsigned algo=1;algo<5;algo++)for(int manual=0;manual<2;manual++){
  bool expected=flags==FE_READY&&algo==MA_FOC&&!manual;
  assert(bool(fe_start_policy(128,flags,algo,manual,5000,5))==expected);
  assert(!fe_start_policy(128,flags,algo,manual,0,5));
  assert(!fe_start_policy(128,flags,algo,manual,6000,5));
  assert(!fe_start_policy(128,flags,algo,manual,5000,6));
 }
 assert(!fe_start_policy(128,FE_READY,2,0,5000,NAN));
 fe_fault=MA_STALE;assert(!fe_profile_allowed(MA_FOC));fe_fault=0;
 uint8_t frame[UV3_FRAME];
 for(unsigned i=0;i<13;i++){uint32_t v;memcpy(&v,(uint8_t*)&model+4*i,4);config(frame,1,i,v);assert(ma_native_config(frame));}
 uint32_t crc=uv3_crc32c((uint8_t*)&model,sizeof(model));
 config(frame,2,128,crc^1);assert(!ma_native_config(frame));
 config(frame,2,128,crc);assert(ma_native_config(frame));
 staged.rs=11.f;stage_mask=8191;config(frame,2,128,uv3_crc32c((uint8_t*)&staged,sizeof(staged)));assert(!ma_native_config(frame));
 assert(ma_native_prepare());fake_bus=320;timer.BDTR=1;
 sample.valid=sample.zero=1;sample.counts[0]=20;sample.counts[1]=-10;
 sample.cycles=cycle.CYCCNT;assert(ma_native_fast(5)==MC_NO_ERROR&&!fe_trial_done);
 assert(fe_trial_begin==cycle.CYCCNT);
 cycle.CYCCNT=fe_trial_begin+5U*SystemCoreClock-1U;
 sample.cycles=estimate_cycles=cycle.CYCCNT;
 assert(ma_native_fast(5)==MC_NO_ERROR&&!fe_trial_done&&timer.BDTR==1);
 cycle.CYCCNT++;sample.cycles=estimate_cycles=cycle.CYCCNT;
 assert(ma_native_fast(5)==MC_NO_ERROR&&fe_trial_done&&timer.BDTR==0&&off_calls==1);
 assert(ma_native_complete()&&!fe_start_policy(128,fe_flags(),2,0,5000,5));
 assert(fe_time_up(100000,100000-850000000U,170000000U));
 assert(!fe_time_up(99999,100000-850000000U,170000000U));
 ma_native_diag(frame,2026102952U);xp_receiver rx={};
 assert(xp_receive(&rx,frame,2026102952U,true,12));
 assert(rx.qualification==128&&rx.experiment_flags==(FE_READY|FE_DONE)&&rx.timing_cases==64);
 for(unsigned i=0;i<UV3_FRAME;i++){frame[i]^=1;assert(!xp_receive(&rx,frame,2026102952U,true,12));frame[i]^=1;}
}
'''
 unit=out/'native_trial.cpp';p.write(unit,pre+source+checks);exe=unit.with_suffix('.exe')
 run=subprocess.run([shutil.which('g++'),'-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
  '-I',str(p.OUT/'nucleo/Inc'),'-I',str(p.OUT/'UNOQ_MOTOR'),str(unit),'-o',str(exe)],capture_output=True,text=True)
 p.write(out/'native_compile.log',run.stdout+run.stderr);run.check_returncode()
 run=subprocess.run([str(exe)],capture_output=True,text=True)
 p.write(out/'native_run.log',run.stdout+run.stderr);run.check_returncode()
 # Prove the runtime profile is the prepared calculation, bit for bit as float32.
 from configure_multi_algorithm import load
 _,raw,q=load(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json')
 assert q==0
 expected=json.loads(p.read(p.ROOT/'artifacts/live_bench_20261029/air56_estimated_foc_r2/profile.json'))['motor']
 assert expected['trip_current']==1.35
 unchanged=[]
 for rel in ('Inc/drive_parameters.h','Inc/power_stage_parameters.h','Inc/current_core.h',
  'Inc/identify_core.h','Inc/current_adc_window_plan.h','Inc/current_adc_deadline.h','Inc/peak_core.h',
  'Src/current_shunt.c','Src/stm32g4xx_mc_it.c','Src/stm32g4xx_hal_msp.c','Src/regular_conversion_manager.c'):
  old=p.read(p.BASE/'nucleo'/rel).replace('2026102940','2026102952')
  assert old==p.read(p.OUT/'nucleo'/rel),rel;unchanged.append(rel)
 old=p.read(p.BASE/'nucleo/Inc/motor_control.h')
 expected=old.replace('fminf(','ma_min2(').replace('fmaxf(','ma_max2(')
 expected=expected.replace('static inline float ma_clip(',p.read(p.ROOT/'tools/foc_trial/fast_math.inc')+'\nstatic inline float ma_clip(')
 expected=expected.replace('const float theta=flux>.0001f?atan2f(x[3],x[2]):0,c0=cosf(theta),s=sinf(theta);',
  'const float c0=flux>.0001f?x[2]/flux:1.f,s=flux>.0001f?x[3]/flux:0.f;')
 assert expected==p.read(p.OUT/'nucleo/Inc/motor_control.h')
 for name in ('MX_TIM1_Init','MX_ADC1_Init','MX_ADC2_Init','SystemClock_Config','uno_clear_frame_is_safe','uno_latch_fault','uno_update_softstart_state'):
  assert function(p.read(p.BASE/'nucleo/Src/main.c'),name)==function(p.read(p.OUT/'nucleo/Src/main.c'),name),name
 for name in ('mi_native_fast','mi_native_config','mi_native_service','mi_native_profile_off'):
  assert function(p.read(p.BASE/'nucleo/Src/multi_native.c'),name)==function(p.read(p.OUT/'nucleo/Src/multi_native.c'),name),name
 probe=function(p.read(p.OUT/'nucleo/Src/multi_native.c'),'fe_profile_tick')+function(p.read(p.OUT/'nucleo/Src/multi_native.c'),'fe_profile_service')
 for forbidden in ('CCR1=','CCR2=','CCR3=','EnableAllOutputs','__disable_irq','AcknowledgeFault','MC_StartMotor'):
  assert forbidden not in probe,forbidden
 # Web START/STOP protections remain byte-for-byte equivalent in their AST.
 def methods(base):
  tree=ast.parse(p.read(base/'web_hmi/server.py'))
  cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='AppState')
  return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}
 a,b=methods(p.BASE),methods(p.OUT)
 for name in ('start_sequence','stop_sequence','_start_without_precharge','operator_heartbeat_fresh'):
  assert a[name]==b[name],name
 report=dict(passed=True,hardware_commands=0,start_commands=0,clear_commands=0,
  native_five_second_stop=True,wraparound_stop=True,calculated_profile_not_identification=True,
  calculated5Hz_bounded5s_gate=True,calculated_profile_persists_without_autostart=True,
  off_probe_no_pwm_writes=True,synthetic_clock_is_not_target_timing=True,
  crc_wire_roundtrip=True,protection_files_unchanged=unchanged,
  prepared_profile_crc32c=__import__('configure_multi_algorithm').crc32c(raw))
 p.write(out/'selftest.json',json.dumps(report,indent=2));print(json.dumps(report))

if __name__=='__main__':main()
