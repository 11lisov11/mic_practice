/* Isolated test only. Normal motor backend and test-edge timer have disjoint ownership. */
#include "main.h"
#include "mc_config.h"
#include "mc_api.h"
#include "pin_pwm_diag.h"
#include "full_mcsdk_diag.h"
#include "edges_mcsdk_diag.h"
#include "stm32g4xx_ll_tim.h"
static volatile uint32_t armed,adc_seen,adc_active,adc_stamp,adc_begin,adc_bad,adc_max;
static uint32_t backend_ready;
void mic_motor_backend_init(void){
 /* Boot/calibration used the original peripherals. No pulses have been enabled.
  * Native V/f safety now owns a real, stopped, non-routed timer. No voltage,
  * fault mask, MCI state, sensor value or safety decision is changed. */
 LL_TIM_DisableAllOutputs(TIM1);
 __HAL_RCC_TIM8_CLK_ENABLE();__HAL_RCC_TIM8_FORCE_RESET();__HAL_RCC_TIM8_RELEASE_RESET();
 TIM8->PSC=0;TIM8->ARR=TIM1->ARR;TIM8->RCR=TIM1->RCR;
 TIM8->CR1=TIM1->CR1&~TIM_CR1_CEN;TIM8->CCER=0;TIM8->DIER=0;
 TIM8->BDTR=TIM1->BDTR&~(TIM_BDTR_MOE|TIM_BDTR_AOE);
 __DMB();PWM_ParamsM1.TIMx=TIM8;__DMB();backend_ready=1;
}
void mic_edges_io_init(void){armed=1;}
void mic_edges_adc_enter(void){
 if(!armed)return;
 const uint32_t now=DWT->CYCCNT;adc_stamp=adc_begin=now;++adc_seen;
 if(mic_pin_active())++adc_active;
 if(((ADC1->ISR|ADC2->ISR)&ADC_ISR_JQOVF)||!(ADC2->ISR&ADC_ISR_JEOS))++adc_bad;
}
void mic_edges_adc_exit(void){
 if(!armed)return;
 const uint32_t cost=DWT->CYCCNT-adc_begin;if(cost>adc_max)adc_max=cost;
}
uint32_t mic_edges_adc_all(void){return adc_seen;}
uint32_t mic_edges_adc_run(void){return adc_active;}
uint32_t mic_edges_adc_bad(void){return adc_bad;}
uint32_t mic_edges_adc_max_cost(void){return adc_max;}
uint32_t mic_edges_backend_flags(void){
 return ((!backend_ready || PWM_ParamsM1.TIMx!=TIM8)?1U:0U) |
  ((TIM8->CR1&TIM_CR1_CEN)?2U:0U) |
  ((TIM8->BDTR&(TIM_BDTR_MOE|TIM_BDTR_AOE))?4U:0U) |
  (TIM8->CCER?8U:0U) |
  ((pACIM_VF_Component_M1->pPWM!=&PWM_ParamsM1)?16U:0U);
}
static uint32_t motor_domain_guard(void){
 uint32_t bad=mic_edges_backend_flags()?1024U:0U;
 /* UV is required to stay ACTIVE, not masked or acknowledged. Any other
  * current/latched motor fault or state transition ends the edge fixture. */
 if(MC_GetCurrentFaultsMotor1()!=MC_UNDER_VOLT || MC_GetOccurredFaultsMotor1()!=MC_UNDER_VOLT)bad|=1024U;
 const MCI_State_t s=MC_GetSTMStateMotor1();
 if(s!=FAULT_NOW && s!=FAULT_OVER)bad|=4096U;
 if(VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super)>=20U)bad|=2048U;
 return bad;
}
uint32_t mic_edges_guard(void){
 const uint32_t seen=adc_seen,stamp=adc_stamp,now=DWT->CYCCNT;
 uint32_t bad=motor_domain_guard()|mic_full_guard();
 if(!armed || seen<100 || (uint32_t)(now-stamp)>SystemCoreClock/200U || adc_bad)bad|=256U;
 return bad;
}
void mic_edges_observe_safety(void){
 /* Native safety has already processed real sensor values/faults and stopped
  * its own TIM8. Propagate every non-baseline fault to physical TIM1 as well. */
 if(mic_pin_active()){
  const uint32_t bad=motor_domain_guard();if(bad)mic_pin_force_abort(bad);
 }
}
