"""Prepare, never install: protected MCSDK/TIM8 plus isolated TIM1 edge fixture."""
import json,os,shutil
from pathlib import Path
import prepare_no_switch_diag as p
from audit_production_pwm_filters import function
OLD=p.ROOT/'artifacts/live_bench_20261028/full_mcsdk_diag_r1'
PIN=p.ROOT/'artifacts/live_bench_20261028/combined_io_diag_r2'
OUT=p.ROOT/'artifacts/live_bench_20261028/full_mcsdk_edges_r1'
BUILD=2026102804
def main():
 OUT.mkdir(parents=True,exist_ok=False);old=json.loads(p.read(OLD/'manifest.json'))
 for rel,h in old['sealed_sha256'].items():assert p.sha(OLD/rel)==h,rel
 def copy(src,dst):
  rel=Path(src).relative_to(OLD/'nucleo')
  if rel.parts[0] in ('Drivers','MCSDK_v6.4.2-Full'):os.link(src,dst);return dst
  return shutil.copy2(src,dst)
 shutil.copytree(OLD/'nucleo',OUT/'nucleo',copy_function=copy,ignore=shutil.ignore_patterns('Debug','Release','__pycache__'))
 for tree in ('build/nucleo','verification','preserved_records','restore'):(OUT/tree).mkdir(parents=True,exist_ok=True)
 shutil.copytree(OLD/'preserved_records',OUT/'preserved_records/earlier',copy_function=os.link)
 for tree in ('run_r1','install_r1','build/nucleo'):shutil.copytree(OLD/tree,OUT/'preserved_records/2803'/tree,copy_function=os.link)
 for name in ('assessment.json','runtime_sha256.json','manifest.json'):shutil.copy2(OLD/name,OUT/'preserved_records/2803'/name)
 for f in (OLD/'restore').iterdir():shutil.copy2(f,OUT/'restore'/f.name)
 for tree in ('Src','Inc'):
  for f in (OUT/'nucleo'/tree).iterdir():
   if f.is_file():
    a=p.read(f);b=a.replace('2026102803',str(BUILD))
    if a!=b:p.write(f,b)
 for name,tree in [('edges_mcsdk_diag.c','Src'),('edges_mcsdk_diag.h','Inc')]:shutil.copy2(p.ROOT/'tools'/name,OUT/'nucleo'/tree/name)
 f=OUT/'nucleo/STM32CubeIDE/.project';s=p.read(f)
 s=p.once(s,'\t<linkedResources>','\t<linkedResources>\n\t\t<link>\n\t\t\t<name>Application/User/edges_mcsdk_diag.c</name>\n\t\t\t<type>1</type>\n\t\t\t<locationURI>PARENT-1-PROJECT_LOC/Src/edges_mcsdk_diag.c</locationURI>\n\t\t</link>');p.write(f,s)
 # Remove the predecessor private no-edge workload, not any MCSDK task.
 p.write(OUT/'nucleo/Src/load_diag.c','''#include "load_diag.h"
bool mic_load_active(void){return false;}
void mic_load_tim_update(void){}
void mic_load_medium_update(void){}
void mic_load_adc_enter(uint32_t now){(void)now;}
void mic_load_adc_exit(uint32_t now,uint32_t good){(void)now;(void)good;}
''')
 f=OUT/'nucleo/Src/main.c';s=p.read(f)
 s=p.once(s,'#include "full_mcsdk_diag.h"','#include "full_mcsdk_diag.h"\n#include "edges_mcsdk_diag.h"\n#include "pin_pwm_diag.h"')
 # The predecessor already uses only native UART command dispatch.
 assert 'mic_combined_uart_poll' not in s
 s=p.once(s,'  /* Set phase GPIO LOW before MCSDK permanently locks its configuration. */\n  mic_load_prepare_pins();\n  MX_MotorControl_Init();','  /* Keep the original six pins on TIM1 AF6; the inverter ribbon is removed. */\n  MX_MotorControl_Init();\n  mic_motor_backend_init();')
 s=p.once(s,'  mic_load_init();\n  mic_full_init();','  mic_full_init();\n  mic_edges_io_init();\n  mic_pin_init();')
 s=p.once(s,'    mic_load_poll();\n    mic_full_publish();','    mic_pin_poll();\n    mic_full_publish();')
 s=p.once(s,'if (LL_TIM_IsEnabledAllOutputs(TIM1)) status |= UNO_STATUS_PWM_ACTIVE | UNO_STATUS_SHUTDOWN_RELEASED;',
  'if (LL_TIM_IsEnabledAllOutputs(PWM_ParamsM1.TIMx)) status |= UNO_STATUS_PWM_ACTIVE | UNO_STATUS_SHUTDOWN_RELEASED; /* Motor status excludes fixture edges. */')
 s=s.replace('!mic_load_active() && !uno_link.command_enabled','!mic_pin_active() && !uno_link.command_enabled')
 # Panic paths stop BOTH physical timer domains before masking interrupts.
 oldbody=function(s,'Error_Handler');newbody=oldbody.replace('{','{\n  LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableAllOutputs(TIM8);',1)
 s=p.once(s,oldbody,newbody);p.write(f,s)
 f=OUT/'nucleo/Src/full_mcsdk_runtime.inc';s=p.read(f)
 s=s.replace('mic_load_active()','mic_pin_active()').replace('return full_uart_faults?256U:0U;','return full_uart_faults?512U:0U;')
 s=p.once(s,'if(uno_rx_errors || uno_rx_overflow || uno_link.bad_count || uno_transport.fault ||','if(uno_link.fault_latched || uno_rx_errors || uno_rx_overflow || uno_link.bad_count || uno_transport.fault ||')
 s=p.once(s,'r[2]=1;r[3]=24;','r[2]=2;r[3]=24;')
 s=p.once(s,'r[17]=uno_link.good_count;r[18]=uno_link.bad_count;','r[17]=TIM8->BDTR;r[18]=uno_link.bad_count;')
 s=p.once(s,'r[19]=mic_full_fixture_denials;r[20]=full_uart_faults;','r[19]=mic_edges_backend_flags();r[20]=full_uart_faults;')
 p.write(f,s)
 f=OUT/'nucleo/Src/stm32g4xx_mc_it.c';s=p.read(f)
 s='#include "edges_mcsdk_diag.h"\n#include "pin_pwm_diag.h"\n'+s
 s=p.once(s,'  mic_current_adc_irq();','  mic_edges_adc_enter();mic_current_adc_irq();mic_edges_adc_exit();')
 s=p.once(s,'   TSK_HighFrequencyTask();','   TSK_HighFrequencyTask();\n   mic_pin_irq();')
 s=p.once(s,'  mic_break_capture_first(HAL_GetTick());','  mic_pin_break();\n  mic_break_capture_first(HAL_GetTick());')
 oldbody=function(s,'HardFault_Handler');newbody=oldbody.replace('{','{\n  LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableAllOutputs(TIM8);',1)
 s=p.once(s,oldbody,newbody);p.write(f,s)
 f=OUT/'nucleo/Src/mc_tasks.c';s=p.read(f)
 s='#include "edges_mcsdk_diag.h"\n'+s
 body=function(s,'TSK_SafetyTask_PWMOFF');pos=body.rfind('}')
 s=p.once(s,body,body[:pos]+'  mic_edges_observe_safety();\n'+body[pos:]);p.write(f,s)
 # Reuse the proven coherent phase/MOE guard and terminal publication.
 f=OUT/'nucleo/Src/pin_pwm_diag.c';s=p.read(PIN/'nucleo/Src/pin_pwm_diag.c')
 s=s.replace('2026102802',str(BUILD))
 s=p.once(s,'#include "combined_io_diag.h"','#include "edges_mcsdk_diag.h"')
 s=p.once(s,' * AS5600 driver is unchanged; no motor-control scheduler/UART/ADC is started.',' * Full native MCSDK/UART/ADC runs; motor PWM backend is non-routed TIM8.')
 s=p.once(s,' return bad|mic_io_guard();',' return bad|mic_edges_guard();')
 s=p.once(s,' LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableIT_UPDATE(TIM1);',' LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableAllOutputs(TIM8);LL_TIM_DisableIT_UPDATE(TIM1);')
 s=p.once(s,'bool mic_pin_active(void){return state==1;}','bool mic_pin_active(void){return state==1;}\nvoid mic_pin_force_abort(uint32_t why){if(state==1)finish(why);}')
 s=p.once(s,' TIM1->EGR=TIM_EGR_UG;TIM1->SR=0;',' if((TIM1->SR&(TIM_SR_BIF|TIM_SR_B2IF)) || !(GPIOA->IDR&GPIO_PIN_6))reason|=4U;\n TIM1->EGR=TIM_EGR_UG;LL_TIM_ClearFlag_UPDATE(TIM1);')
 # Require live UV/zero bus and a disabled independent motor backend throughout.
 s=p.once(s,' if(ACIM_VF_Controller(&replay)){finish(64);return;}',''' /* A private stack handle directs only this modulation call to TIM1.
  * Never mutate the MCSDK-owned PWM handle or timer binding. */
 PWM_Handle_t fixture_pwm=*replay.pPWM;fixture_pwm.TIMx=TIM1;
 PWM_Handle_t *const motor_pwm=replay.pPWM;replay.pPWM=&fixture_pwm;
 const uint16_t calc_status=ACIM_VF_Controller(&replay);replay.pPWM=motor_pwm;
 if(calc_status){finish(64);return;}''')
 # Schema2 repurposes four diagnostic-only slots for real ADC observer counts.
 s=p.once(s,'v[1]=1;','v[1]=2;')
 s=p.once(s,' v[24]=mic_local_stop_latched;v[25]=TIM1->RCR;v[26]=RCC->AHB2ENR;v[27]=TIM1->PSC;',' v[24]=mic_local_stop_latched;v[25]=TIM1->RCR;v[26]=mic_edges_adc_all();v[27]=mic_edges_adc_bad();')
 s=p.once(s,'v[57]=break_sr;v[58]=TIM1->SMCR;v[59]=TIM1->DIER;v[60]=SysTick->LOAD;','v[57]=break_sr;v[58]=mic_edges_adc_run();v[59]=TIM1->DIER;v[60]=mic_edges_adc_max_cost();')
 p.write(f,s)
 m=dict(schema='mic_ai.full_mcsdk_real_edges.v1',build=BUILD,built=False,installed=False,hardware_tested=False,
  preparation_only=True,MCSDK_motor_timer='TIM8; CEN0/CCER0/MOE0, no GPIO routed',diagnostic_timer='TIM1 original AF6 six pins',
  full_native_MCSDK_boot_scheduler_safety_commands=True,MCSDK_UV_required_active=True,Vbus_required_below20=True,
  native_thresholds_unchanged=True,actual_bus_never_forged=True,normal_motor_START_inhibited=True,
  TIM1_hardware_BKIN_deadtime_unchanged=True,auto_stop_ms=5000,one_request_per_boot=True,
  stages_ms=[1000,2000,2000],old_record_files_preserved=True,
  limitations=['Two timer domains; not normal production TIM1 motor RUN','Inverter ribbon MUST stay disconnected, J1/J4 OFF','ADC values not qualified motor amps/RMS','Digital Saleae cannot qualify analog ringing/sub125ns'],
  archived={f.relative_to(OUT/'preserved_records').as_posix():p.sha(f) for f in (OUT/'preserved_records').rglob('*') if f.is_file()})
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n');print(json.dumps(dict(prepared=True,build=BUILD,archived=len(m['archived']),hardware_calls=0)))
if __name__=='__main__':main()
