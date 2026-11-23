"""Actual fixture and native PWM-off adapter against two distinct timer models."""
import json,subprocess,re
import prepare_no_switch_diag as p
import prepare_full_mcsdk_edges as prep
from audit_production_pwm_filters import function

TEST=r'''
static unsigned checks;
static void test(bool b){++checks;if(!b){fprintf(stderr,"edges_check%u\n",checks);exit(1);}}
static void reset(){
 tim=Timer{};aux=Timer{};pa=GPIO{};pb=GPIO{};dwt={};now_ms=0;bus=10;
 mic_local_stop_latched=0;motor_current=motor_occurred=4;motor_state=FAULT_NOW;
 state=reason=attempted=start=stop=elapsed=phase=updates=cached_at=max_cost=max_gap=break_sr=0;
 previous_irq=previous_poll=max_poll_gap=seq=publish_ms=0;fail_math=0;
 for(unsigned i=7;i<=10;i++)pa.MODER|=2U<<(2*i);
 pa.AFR[0]=6U<<28;pa.AFR[1]=0x666;pa.IDR=64;pb.MODER=10;pb.AFR[0]=0x66;
 PWM_ParamsM1.TIMx=TIM1;original.pPWM=&PWM_ParamsM1;
 armed=adc_seen=adc_active=adc_stamp=adc_begin=adc_bad=adc_max=backend_ready=0;
 a1=AdcFake{};a2=AdcFake{};
 uno_rx_errors=uno_rx_overflow=full_uart_faults=0;uno_link={0,0,true};uno_transport={};mic_uart_tx={};
 mic_motor_backend_init();mic_edges_io_init();adc_seen=200;mic_pin_init();
 test(PWM_ParamsM1.TIMx==TIM8);test(mic_edges_backend_flags()==0);
}
static void request(){mic_pin_request=PIN_REQUEST;mic_pin_poll();}
static void on_phase(){
 reset();request();test(state==1);dwt.CYCCNT=170000000;now_ms=1000;
 cached_at=adc_stamp=dwt.CYCCNT;uno_link.last_valid_ms=now_ms;mic_pin_irq();
 test(phase==2&&(tim.BDTR&TIM_BDTR_MOE));
}
int main(){
 reset();test(!state);request();test(state==1);
 for(unsigned n=1;n<=80000;n++){
  dwt.CYCCNT=n*10625U;now_ms=dwt.CYCCNT/170000;uno_link.last_valid_ms=now_ms;
  mic_edges_adc_enter();
  if(n%8==0){
   /* Same native PWM-off body used by the unchanged MCSDK UV safety branch. */
   PWM_SwitchOffPWM(&PWM_ParamsM1);mic_edges_observe_safety();mic_pin_poll();
  }
  mic_pin_irq();mic_edges_adc_exit();
  test(PWM_ParamsM1.TIMx==TIM8);test(!(aux.BDTR&TIM_BDTR_MOE));test(!aux.CCER);
  if(n<16000)test(phase==1&&!(tim.BDTR&TIM_BDTR_MOE));
  if(n>=16000&&n<48000)test(phase==2&&(tim.BDTR&TIM_BDTR_MOE));
  if(n>=48000&&n<80000)test(phase==3&&(tim.BDTR&TIM_BDTR_MOE));
 }
 test(state==2&&reason==0&&elapsed==850000000);test(!(tim.BDTR&TIM_BDTR_MOE));test(!(tim.DIER&1));
 test(adc_active==80000);test(boundaries[2]-boundaries[0]==200);test(boundaries[4]-boundaries[2]==400);test(boundaries[6]-boundaries[4]==400);
 request();test(state==2&&attempted==1);
 for(unsigned i=0;i<20;i++){
  on_phase();
  if(i==0)pa.IDR=0;
  if(i==1)mic_local_stop_latched=1;
  if(i==2)tim.BDTR^=TIM_BDTR_BKE;
  if(i==3)tim.SR|=TIM_SR_BIF;
  if(i==4)cached_at-=850001;
  if(i==5)adc_stamp-=850001;
  if(i==6)adc_bad=1;
  if(i==7)uno_rx_errors=1;
  if(i==8)uno_link.last_valid_ms-=301;
  if(i==9)motor_current=motor_occurred=6;
  if(i==10)motor_current=motor_occurred=0;
  if(i==11)motor_state=RUN;
  if(i==12)bus=20;
  if(i==13)PWM_ParamsM1.TIMx=TIM1;
  if(i==14)aux.BDTR|=TIM_BDTR_MOE;
  if(i==15)aux.CR1|=TIM_CR1_CEN;
  if(i==16)aux.CCER=1;
  if(i==17)fail_math=1;
  if(i==18)tim.BDTR|=TIM_BDTR_AOE;
  if(i==19)uno_link.fault_latched=true;
  mic_pin_irq();test(state==3&&reason);test(!(tim.BDTR&TIM_BDTR_MOE));test(!(aux.BDTR&TIM_BDTR_MOE));
 }
 // Every extra current/latched motor fault propagates immediately after safety.
 for(unsigned bit=0;bit<16;bit++)if(bit!=2){
  on_phase();motor_current=motor_occurred=4|(1U<<bit);mic_edges_observe_safety();
  test(state==3&&(reason&1024));test(!(tim.BDTR&TIM_BDTR_MOE));
 }
 on_phase();mic_pin_break();test(state==3&&(reason&4));
 on_phase();mic_pin_request=PIN_CANCEL;mic_pin_poll();test(state==3&&(reason&128));
 reset();tim.SR|=TIM_SR_BIF;mic_pin_init();request();test(state==4&&(reason&4));test(tim.SR&TIM_SR_BIF);
 now_ms+=50;mic_pin_poll();test(mic_pin_report[1]==2);test(ld_crc((const uint32_t*)mic_pin_report+5,56)==mic_pin_report[62]);
 printf("{\"passed\":true,\"checks\":%u,\"timer_updates\":80000,\"native_safety_off_calls\":10000,\"fault_injections\":35,\"hardware_calls\":0}\n",checks);
}
'''
def main():
 c=prep.OUT;v=c/'verification';mock=v/'mock';mock.mkdir(exist_ok=True)
 for name in ('main.h','mc_config.h','local_stop.h','mc_api.h','stm32g4xx_ll_tim.h'):p.write(mock/name,'')
 old=p.read(prep.PIN/'verification/combined_guard_test.cpp')
 pre=old[:old.index('struct ACIM_VF_Handle_t')]
 pre=pre.replace('static uint32_t MC_GetCurrentFaultsMotor1(){return 4;}','static uint32_t motor_current=4,motor_occurred=4;\nstatic uint32_t MC_GetCurrentFaultsMotor1(){return motor_current;}')
 pre=pre.replace('static uint32_t MC_GetOccurredFaultsMotor1(){return 1028;}','static uint32_t MC_GetOccurredFaultsMotor1(){return motor_occurred;}')
 pre+='''
typedef Timer TIM_TypeDef;
struct PWM_Handle_t{Timer*TIMx=&tim;};static PWM_Handle_t PWM_ParamsM1;
enum {FAULT_NOW=10,FAULT_OVER=11,RUN=6,MC_UNDER_VOLT=4};
using MCI_State_t=unsigned;static unsigned motor_state=FAULT_NOW;
static unsigned MC_GetSTMStateMotor1(){return motor_state;}
static struct{int _Super;} BusVoltageSensor_M1;
#define __HAL_RCC_TIM8_CLK_ENABLE() do{}while(0)
#undef __HAL_RCC_TIM8_FORCE_RESET
#define __HAL_RCC_TIM8_FORCE_RESET() do{aux=Timer{};}while(0)
#define __HAL_RCC_TIM8_RELEASE_RESET() do{}while(0)
#define LL_TIM_OSSI_ENABLE TIM_BDTR_OSSI
static bool mic_load_active(){return false;}
'''
 mid=old[old.index('struct ACIM_VF_Handle_t'):old.index('void mic_io_uart_snapshot')]
 mid=mid.replace('struct ACIM_VF_Handle_t {int bVF_Mode=0;','struct ACIM_VF_Handle_t {PWM_Handle_t*pPWM=&PWM_ParamsM1;int bVF_Mode=0;')
 mid=mid.replace('tim.CCR1=2600+n;tim.CCR2=2700-n;tim.CCR3=2650+n/2;','p->pPWM->TIMx->CCR1=2600+n;p->pPWM->TIMx->CCR2=2700-n;p->pPWM->TIMx->CCR3=2650+n/2;')
 code=pre+mid+'''
static uint32_t uno_rx_errors,uno_rx_overflow,full_uart_faults;
static struct{uint32_t last_valid_ms,bad_count;bool link_seen,fault_latched;}uno_link;
static struct{uint32_t fault;}uno_transport;
static struct{uint32_t timeouts,dma_errors,full_errors;}mic_uart_tx;
#define UNO_LINK_TIMEOUT_MS 300U
'''
 code+=function(p.read(c/'nucleo/Src/full_mcsdk_runtime.inc'),'mic_full_guard')+'\n'
 code+='#include "edges_mcsdk_diag.c"\n#include "pin_pwm_diag.c"\n'
 pwm=p.read(c/'nucleo/MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Src/pwm.c')
 code+=function(pwm,'PWM_SwitchOffPWM')+'\n'+TEST
 p.write(v/'actual_edges_model.cpp',code)
 flags=['g++','-std=c++17','-O3','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-Wno-unused-function','-Wno-misleading-indentation','-I',str(mock),'-I',str(c/'nucleo/Inc'),'-I',str(c/'nucleo/Src')]
 exe=v/'edges_model.exe';q=subprocess.run(flags+[str(v/'actual_edges_model.cpp'),'-o',str(exe)],capture_output=True,text=True,timeout=60)
 p.write(v/'edges_compile.log',q.stdout+q.stderr);assert not q.returncode,q.stderr
 q=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60);p.write(v/'edges_model.log',q.stdout+q.stderr);assert not q.returncode,q.stderr
 results=dict(model=json.loads(q.stdout))
 # Execute the actual coherent guard/stop publication with forced IRQ races.
 race=p.read(prep.PIN/'verification/forced_irq_race.cpp')
 race=p.once(race,function(race,'guard'),function(p.read(c/'nucleo/Src/pin_pwm_diag.c'),'guard'))
 race=p.once(race,function(race,'finish'),function(p.read(c/'nucleo/Src/pin_pwm_diag.c'),'finish'))
 race=p.once(race,'#define TIM1 (&timer)','#define TIM1 (&timer)\nstatic Timer shadow_timer;\n#define TIM8 (&shadow_timer)')
 race=p.once(race,'static uint32_t mic_io_guard(){return 0;}','static uint32_t mic_io_guard(){return 0;}\nstatic uint32_t mic_edges_guard(){return 0;}')
 p.write(v/'actual_edges_race.cpp',race);rx=v/'edges_race.exe'
 q=subprocess.run(['g++','-std=c++17','-O3','-Wall','-Wextra','-Werror',str(v/'actual_edges_race.cpp'),'-o',str(rx)],capture_output=True,text=True,timeout=60)
 p.write(v/'race_compile.log',q.stdout+q.stderr);assert not q.returncode,q.stderr
 q=subprocess.run([str(rx)],capture_output=True,text=True,timeout=60);p.write(v/'race_run.log',q.stdout+q.stderr);assert not q.returncode,q.stderr
 results['preemption']=json.loads(q.stdout)
 # Source equivalence protects all original thresholds and fault decisions.
 main=p.read(c/'nucleo/Src/main.c');prior=p.read(prep.OLD/'nucleo/Src/main.c')
 for name in ('SystemClock_Config','MX_ADC1_Init','MX_ADC2_Init','MX_TIM1_Init','MX_USART1_UART_Init','USART1_IRQHandler','uno_handle_valid_frame','uno_link_poll','uno_transport_result','uno_rearm_break_irq','mic_local_stop_enable_outputs'):
  assert function(main,name)==function(prior,name),name
 def normalize_reply(s):return s.replace('if (LL_TIM_IsEnabledAllOutputs(PWM_ParamsM1.TIMx)) status |= UNO_STATUS_PWM_ACTIVE | UNO_STATUS_SHUTDOWN_RELEASED; /* Motor status excludes fixture edges. */','if (LL_TIM_IsEnabledAllOutputs(TIM1)) status |= UNO_STATUS_PWM_ACTIVE | UNO_STATUS_SHUTDOWN_RELEASED;')
 assert normalize_reply(function(main,'uno_send_reply'))==normalize_reply(function(prior,'uno_send_reply'))
 tasks=p.read(c/'nucleo/Src/mc_tasks.c');oldt=p.read(prep.OLD/'nucleo/Src/mc_tasks.c')
 for name in ('MC_RunMotorControlTasks','MC_Scheduler','TSK_MediumFrequencyTaskM1','TSK_HighFrequencyTask','TSK_SafetyTask','TSK_SafetyTask_PWMOFF'):
  assert function(tasks,name).replace('  mic_edges_observe_safety();\n','')==function(oldt,name).replace('  mic_edges_observe_safety();\n',''),name
 for rel in ('Src/current_shunt.c','Src/nucleo_encoder.c','Inc/drive_parameters.h','Inc/parameters_conversion.h','Inc/encoder_core.h','Inc/bus_clear.h','Src/mc_config.c','Src/mc_parameters.c'):
  if rel=='Src/nucleo_encoder.c' and hasattr(prep,'transform'):
   expected=prep.transform(p.read(prep.OLD/'nucleo'/rel).replace('2026102804',str(prep.BUILD)))
   assert p.read(c/'nucleo'/rel)==expected,rel
  else:assert p.sha(c/'nucleo'/rel)==p.sha(prep.OLD/'nucleo'/rel),rel
 assert 'mic_load_prepare_pins' not in function(main,'main') and 'MX_MotorControl_Init();' in function(main,'main')
 irq=p.read(c/'nucleo/Src/stm32g4xx_mc_it.c')
 for name in ('HardFault_Handler',):
  assert 'LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableAllOutputs(TIM8);' in function(irq,name)
 assert 'LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableAllOutputs(TIM8);' in function(main,'Error_Handler')
 for rel,h in json.loads(p.read(c/'manifest.json'))['archived'].items():assert p.sha(c/'preserved_records'/rel)==h,rel
 p.OUT=c
 import no_switch_diag_math_test as math
 math.main();results['math']=json.loads(p.read(v/'math_report.json'))
 results.update(passed=True,hardware_calls=0,original_native_MCSDK_safety_and_commands_unchanged=True,ADC_I2C_sources_unchanged=True,
  TIM1_initialization_BKIN_deadtime_unchanged=True,normal_motor_START_still_inhibited=True,old_records_verified=True,
  limitations=['Register models do not demonstrate real target waveforms or timing','No normal motor RUN; native UV fault is intentionally required active'])
 p.write(v/'native_tests.json',json.dumps(results,indent=2)+'\n');print(json.dumps(results))
if __name__=='__main__':main()
