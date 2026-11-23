"""One persistent calculated profile + bounded FOC trial. Preparation only."""
import json,os,shutil
from pathlib import Path
from prepare_standstill_commissioning import ROOT,read,write,once
BASE=ROOT/'artifacts/live_bench_20261029/adc_noise_rpc_fix_r1'
OUT=ROOT/'artifacts/live_bench_20261029/estimated_foc_trial_r5'
NEW=(2026102951,2026102952)

def main():
 assert not OUT.exists()
 for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
  def copy(src,dst):
   rel=Path(src).relative_to(BASE/folder)
   if folder=='libraries' or (folder=='nucleo' and rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full')):
    os.link(src,dst);return dst
   return shutil.copy2(src,dst)
  shutil.copytree(BASE/folder,OUT/folder,copy_function=copy,
   ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
 for folder in ('nucleo/Src','nucleo/Inc','UNOQ_MOTOR','web_hmi'):
  for f in (OUT/folder).rglob('*'):
   if f.is_file():
    old=read(f);new=old.replace('2026102941',str(NEW[0])).replace('2026102940',str(NEW[1]))
    if old!=new:write(f,new)
 for folder in ('nucleo/Inc','UNOQ_MOTOR'):
  write(OUT/folder/'foc_experiment.h',read(ROOT/'tools/foc_trial/foc_experiment.h'))
 f=OUT/'nucleo/Inc/motor_control.h';s=read(f)
 s=s.replace('fminf(','ma_min2(').replace('fmaxf(','ma_max2(')
 s=once(s,'static inline float ma_clip(',read(ROOT/'tools/foc_trial/fast_math.inc')+'\nstatic inline float ma_clip(');write(f,s)
 s=once(s,'const float theta=flux>.0001f?atan2f(x[3],x[2]):0,c0=cosf(theta),s=sinf(theta);',
  'const float c0=flux>.0001f?x[2]/flux:1.f,s=flux>.0001f?x[3]/flux:0.f;');write(f,s)
 f=OUT/'nucleo/Src/multi_native.c';s=read(f)
 s=once(s,'#include "motor_control.h"','#include "motor_control.h"\n#include "foc_experiment.h"')
 s=once(s,'static ma_motor model,staged;','static ma_motor model=FE_ESTIMATED_MOTOR,staged;')
 s=once(s,'selected=MA_VF,profile_ready,qualification,running,first_fault,run_fault;',
  'selected=MA_VF,profile_ready=1,qualification=FE_ESTIMATED,running,first_fault,run_fault;')
 s=once(s,'static uint32_t max_fast_cycles,max_observer_cycles;',
 '''static uint32_t max_fast_cycles,max_observer_cycles;
static unsigned fe_flags(void);static int fe_profile_allowed(unsigned);
static int fe_profile_tick(void);static void fe_profile_service(void);
static volatile uint8_t fe_trial_done;
static uint32_t fe_trial_begin;''')
 s=s.replace('!profile_ready||qualification!=7','!fe_profile_allowed(selected)')
 s=once(s,'if(algorithm!=MA_VF&&(!fe_profile_allowed(selected)))return 0;',
  'if(algorithm!=MA_VF&&!fe_profile_allowed(algorithm))return 0;')
 s=once(s,'running=0;run_fault=0;ma_reset(&observer,&controller);',
  'running=0;run_fault=0;fe_trial_done=0;ma_reset(&observer,&controller);')
 s=once(s,'if(index>7||stage_mask!=8191||',
  'if((index>7&&index!=FE_ESTIMATED)||stage_mask!=8191||')
 s=once(s,'model=staged;qualification=(uint8_t)index;profile_ready=1;stage_mask=0;',
 '''if(index==FE_ESTIMATED&&!fe_model_exact(&staged))return 0;
    model=staged;qualification=(uint8_t)index;profile_ready=1;stage_mask=0;''')
 s=once(s,'selected=(uint8_t)index;ma_reset(&observer,&controller);return 1;',
  'selected=(uint8_t)index;fe_trial_done=0;ma_reset(&observer,&controller);return 1;')
 s=once(s,'if(id_profile_running)return;','if(id_profile_running){ma_profile_kick();return;}\n  fe_profile_service();ma_profile_kick();')
 s=once(s,'if(run_fault)return MC_SW_ERROR;', '''if(run_fault)return MC_SW_ERROR;
  if(qualification==FE_ESTIMATED){
    if(fe_trial_done){PWM_SwitchOffPWM(&PWM_ParamsM1);return MC_NO_ERROR;}
    if(!isfinite(reference_hz)||reference_hz<0||reference_hz>5.001f){ma_fail(MA_INVALID);return MC_SW_ERROR;}
    if(!running)fe_trial_begin=begin;
    if(running&&fe_time_up(begin,fe_trial_begin,SystemCoreClock)){
      fe_trial_done=1;PWM_SwitchOffPWM(&PWM_ParamsM1);running=0;return MC_NO_ERROR;
    }
  }''')
 s=once(s,'p[2]=0xE4;p[3]=3;', 'p[2]=0xE4;p[3]=4;')
 s=once(s,'running&&profile_ready&&qualification==7&&observer.steps>=500&&',
  'running&&fe_profile_allowed(selected)&&observer.steps>=500&&')
 s=once(s,'ma_put(p+19,max_fast_cycles);ma_put(p+23,max_observer_cycles);',
 '''ma_put(p+19,max_fast_cycles>fe_fast_cycles?max_fast_cycles:fe_fast_cycles);
  ma_put(p+23,max_observer_cycles>fe_observer_cycles?max_observer_cycles:fe_observer_cycles);''')
 # Timing variables must be declared before diagnostics; definitions in the
 # appended implementation otherwise cannot be referenced by earlier functions.
 s=once(s,'static unsigned fe_flags(void);',
  'static uint32_t fe_fast_cycles,fe_observer_cycles;static uint8_t fe_fault,fe_case;\nstatic unsigned fe_flags(void);')
 s=once(s,'  uv3_seal(p);\n}\n\n/* Native commissioning additions;',
  '  p[36]=(uint8_t)fe_flags();p[37]=fe_fault;p[38]=fe_case;uv3_seal(p);\n}\n\n/* Native commissioning additions;')
 s=once(s,'int ma_native_complete(void){return selected==4&&id_state.done;}',
  'int ma_native_complete(void){return (selected==4&&id_state.done)||(qualification==FE_ESTIMATED&&selected==MA_FOC&&fe_trial_done);}')
 s=once(s,'void ma_native_profile_tick(void){','void ma_native_profile_tick(void){\n if(fe_profile_tick())return;')
 profile=read(ROOT/'tools/foc_trial/native_profile.inc')
 profile=profile.replace('static uint8_t fe_started,fe_complete,fe_fault,fe_case,fe_n;',
                         'static uint8_t fe_started,fe_complete,fe_n;')
 profile=profile.replace('static uint32_t fe_fast_cycles,fe_observer_cycles;\n','')
 profile=profile.replace('static volatile uint8_t fe_trial_done;\nstatic uint32_t fe_trial_begin;\n','')
 s+='\n'+profile;write(f,s)
 f=OUT/'nucleo/Src/main.c';s=read(f)
 s=once(s,'  if((uint32_t)(now_ms-last_ms)<1000U ||',
  '  if((uint32_t)(now_ms-last_ms)<100U ||')
 s=once(s,'mic_send_break_page(now_ms);mic_send_current_page(now_ms);mic_send_peak_page(now_ms);mic_send_noise_page(now_ms);mic_send_research_page(now_ms);mic_send_identification(now_ms);',
  'mic_send_research_page(now_ms);mic_send_break_page(now_ms);mic_send_current_page(now_ms);mic_send_peak_page(now_ms);mic_send_noise_page(now_ms);mic_send_identification(now_ms);')
 s=once(s,'if(mode==9U&&ma_native_complete()){uno_stop_motor();return;}',
  'if((mode==9U||mode==6U)&&ma_native_complete()){uno_stop_motor();return;}')
 # Enforce the experimental5Hz bound from the requested UART target as well
 # as from the ramped reference consumed by the interrupt.
 anchor='  if(!ma_native_request(algorithm)){'
 s=once(s,anchor,'''  if(!ma_native_reference_allowed(algorithm,frequency_millihz)){
    uno_latch_fault_reason(UNO_FAULT_INTERNAL,UNO_DIAG_FREQUENCY);return;
  }
'''+anchor);write(f,s)
 f=OUT/'nucleo/Inc/multi_native.h';s=read(f)
 s=once(s,'unsigned ma_native_selected(void);','unsigned ma_native_selected(void);\nint ma_native_reference_allowed(unsigned algorithm,uint32_t millihz);');write(f,s)
 f=OUT/'nucleo/Src/multi_native.c';s=read(f)
 s+='''
int ma_native_reference_allowed(unsigned algorithm,uint32_t millihz){
 return qualification!=FE_ESTIMATED||algorithm==MA_VF||
   (algorithm==MA_FOC&&millihz>0&&millihz<=5000U);
}
''';write(f,s)
 s=once(s,'static unsigned fe_flags(void);','static void ma_profile_kick(void);\nstatic unsigned fe_flags(void);')
 s+='''
/* Pend the real TIM1 vector for CPU-only work while MOE0, without enabling PWM. */
static void ma_profile_kick(void){
 if(!LL_TIM_IsEnabledAllOutputs(TIM1)&&
    VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)<=20U&&
    (id_profile_pending||fe_pending))NVIC_SetPendingIRQ(TIM1_UP_TIM16_IRQn);
}
''';write(f,s)
 f=OUT/'UNOQ_MOTOR/research_wire.h';s=read(f).replace('XP_FORMAT=3','XP_FORMAT=4')
 s=once(s,'estimate_valid;float rpm_est;', 'estimate_valid,experiment_flags,timing_fault,timing_cases;float rpm_est;')
 s=once(s,'p[14]<=7&&p[15]<=1&&p[17]<=1&&p[31]<=1&&p[36]==0&&p[37]==0&&p[38]==0;',
  '(p[14]<=7||p[14]==128)&&p[15]<=1&&p[17]<=1&&p[31]<=1&&p[36]<=7&&p[37]<=7&&p[38]<=64;')
 s=once(s,'r->profile_ready=p[15];r->fault=p[16];',
  'r->experiment_flags=p[36];r->timing_fault=p[37];r->timing_cases=p[38];\n r->profile_ready=p[15];r->fault=p[16];');write(f,s)
 write(OUT/'nucleo/Inc/research_wire.h',s)
 f=OUT/'UNOQ_MOTOR/UNOQ_MOTOR.ino';s=read(f)
 s=once(s,'#include "research_wire.h"','#include "research_wire.h"\n#include "foc_experiment.h"')
 # The policy header uses the portable motor structure; include its identical
 # non-HAL dependencies for compiling the shared pure policy in Uno as well.
 for name in ('motor_control.h','current_adc_window_plan.h'):
  write(OUT/'UNOQ_MOTOR'/name,read(OUT/'nucleo/Inc'/name))
 s=once(s,'if(g_ma_algorithm!=1&&g_ma_algorithm!=4&&(!g_research_caps.profile_ready||g_research_caps.qualification!=7))\n    return "FOC requires identified model, amp scale and target timing evidence";',
 '''if(g_ma_algorithm!=1&&g_ma_algorithm!=4&&(!g_research_caps.profile_ready||
      !fe_start_policy(g_research_caps.qualification,g_research_caps.experiment_flags,
        g_ma_algorithm,g_manual_scalar_mode,g_run_limit_ms,g_freq_cmd)))
    return "FOC calculated trial requires timing ready, bounded5s and0to5Hz";''')
 s=once(s,'||op<1||op>2||index>12)return false;',
  '||op<1||op>2||(op==1?index>12:(index>7&&index!=128)))return false;')
 anchor='    s += " algorithm_profile_crc=";s += String((unsigned long)g_research_caps.profile_crc);'
 s=once(s,anchor,anchor+'''
    s += " foc_experiment_flags=";s += String((unsigned)g_research_caps.experiment_flags);
    s += " foc_timing_fault=";s += String((unsigned)g_research_caps.timing_fault);
    s += " foc_timing_cases=";s += String((unsigned)g_research_caps.timing_cases);''');write(f,s)
 f=OUT/'web_hmi/server.py';s=read(f)
 anchor='                "algorithm_profile_crc": int(kv.get("algorithm_profile_crc","0")),'
 s=once(s,anchor,anchor+'''
                "foc_experiment_flags": int(kv.get("foc_experiment_flags","0")),
                "foc_timing_fault": int(kv.get("foc_timing_fault","0")),
                "foc_timing_cases": int(kv.get("foc_timing_cases","0")),''')
 anchor="    data['research_missing_motor_parameters']=['Rr','Lls','Llr','Lms','Imagn']"
 s=once(s,anchor,'''    estimated=data.get('algorithm_qualification')==128
    data['algorithm_profile_kind']='calculated_experimental' if estimated else 'identified' if data.get('algorithm_qualification')==7 else 'unqualified'
    data['research_missing_motor_parameters']=[] if estimated else ['Rr','Lls','Llr','Lms','Imagn']
    data['foc_experiment_max_hz']=5 if estimated else None
    data['foc_experiment_runlimit_s']=5 if estimated else None
    data['foc_timing_ready']=estimated and bool(data.get('foc_experiment_flags',0)&1) and not data.get('foc_timing_fault',0)''')
 anchor="        ready=native and (name=='VF_FIXED' or name in ('FOC_FIXED','ADAPTIVE_PWM') and data.get('algorithm_qualification')==7)"
 s=once(s,anchor,anchor+"\n        if name=='FOC_FIXED' and native and data.get('algorithm_qualification')==128:\n            ready=bool(data.get('foc_experiment_flags',0)&1) and not data.get('foc_timing_fault',0)")
 s=once(s,"        if ready:code,text='','Алгоритм доступен; перед пуском проверяются питание, токи и защиты.'",
 "        if ready:code,text='',('Расчётный FOC: только0–5Гц,5сек,без нагрузки; скорость оценочная.' if name=='FOC_FIXED' and data.get('algorithm_qualification')==128 else 'Алгоритм доступен; перед пуском проверяются питание, токи и защиты.')")
 write(f,s)
 f=OUT/'web_hmi/static/index.html';write(f,read(f).replace('2941-noise-rpc','2951-calculated-foc'))
 write(OUT/'manifest.json',json.dumps(dict(schema='mic_ai.estimated_foc_trial.v1',pair=list(NEW),
  base_pair=[2026102941,2026102940],built=False,installed=False,
  motor_profile='calculated_experimental',raw_protection_thresholds_changed=False,
  active_adc_sampling_changed=False,start_commands=0,clear_commands=0,
  native_auto_stop_seconds=5,experimental_max_hz=5),indent=2))
 print('Prepared2951/2952; calculated candidate persists at boot, no auto START')

if __name__=='__main__':main()
