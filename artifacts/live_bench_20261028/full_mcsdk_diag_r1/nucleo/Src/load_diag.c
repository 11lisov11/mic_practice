/* COMPUTATION-ONLY IMAGE: phase pins are GPIO LOW, actual MOE stays zero.
 * No motor START, no synthetic voltage sent to MCSDK or bus protection.
 * A private VF copy replays the327V modulation normalization only.
 * One request per boot; DWT deadline is checked in TIM IRQ and foreground.
 * AS5600 state machine/timing and all safety task thresholds are unchanged.
 */
#include "main.h"
#include "mc_config.h"
#include "mc_api.h"
#include "local_stop.h"
#include "load_diag.h"
#include "full_mcsdk_diag.h"
#include "load_core.h"
#include "stm32g4xx_ll_tim.h"
#include <string.h>

volatile uint32_t mic_load_request;
volatile uint32_t mic_load_report[LD_REPORT_WORDS];
static volatile ld_core core;
static ACIM_VF_Handle_t replay;
static RampExtMngr_Handle_t replay_ramp;
static volatile uint32_t cached_bad,cached_at,adc_at,adc_seen;
static volatile uint32_t updates,adc_calls,adc_accepted;
static volatile uint32_t medium_updates;
static volatile uint32_t tim_max_cycles,adc_max_cycles,tim_max_gap,adc_max_gap;
static uint32_t tim_previous,adc_previous,adc_begin,protection,seq,publish_at;
static volatile uint32_t guard_adc_stamp,guard_cache_stamp,guard_clock;
static uint32_t ccr_min[3],ccr_max[3],poll_previous,poll_max_gap;
static uint32_t saved_ccr[4],cleanup_done;
static uint32_t pa_mask(void){return GPIO_PIN_7|GPIO_PIN_8|GPIO_PIN_9|GPIO_PIN_10;}
static uint32_t pb_mask(void){return GPIO_PIN_0|GPIO_PIN_1;}
static uint32_t mode_mask(uint32_t pins){
  uint32_t m=0;for(unsigned i=0;i<16;i++)if(pins&(1U<<i))m|=3U<<(2*i);return m;
}
static uint32_t output_mode(uint32_t pins){
  uint32_t m=0;for(unsigned i=0;i<16;i++)if(pins&(1U<<i))m|=1U<<(2*i);return m;
}
static bool pins_low(void){
  return (GPIOA->MODER&mode_mask(pa_mask()))==output_mode(pa_mask()) &&
    (GPIOB->MODER&mode_mask(pb_mask()))==output_mode(pb_mask()) &&
    !(GPIOA->ODR&pa_mask()) && !(GPIOB->ODR&pb_mask()) &&
    !(GPIOA->IDR&pa_mask()) && !(GPIOB->IDR&pb_mask());
}
static uint32_t safety_bits(void){
  return TIM1->BDTR&~(TIM_BDTR_MOE|TIM_BDTR_OSSI|TIM_BDTR_OSSR);
}
static uint32_t guard(void){
  /* Read ISR-produced timestamps before reading the current clock.
   * If an ADC IRQ preempts us, its newer timestamp cannot underflow age. */
  uint32_t bad=cached_bad;
  const uint32_t seen=adc_seen,adc_stamp=adc_at,cache_stamp=cached_at;
  const uint32_t now=DWT->CYCCNT;
  guard_adc_stamp=adc_stamp;guard_cache_stamp=cache_stamp;guard_clock=now;
  if(TIM1->BDTR&TIM_BDTR_MOE)bad|=LD_OUTPUT;
  if(safety_bits()!=protection)bad|=LD_CONFIG;
  if(!seen || (uint32_t)(now-adc_stamp)>SystemCoreClock/200U ||
     (uint32_t)(now-cache_stamp)>SystemCoreClock/200U)bad|=LD_ADC_STALE;
  if(mic_local_stop_latched)bad|=LD_LOCAL_STOP;
  return bad|mic_full_guard();
}
bool mic_load_active(void){return core.state==LD_RUNNING;}
static void stop_outputs(void){LL_TIM_DisableAllOutputs(TIM1);}

void mic_load_prepare_pins(void){
  stop_outputs();
  /* Independent physical-pin inhibit; leave PA6/BKIN/PA4 capture untouched. */
  GPIO_InitTypeDef g={0};g.Mode=GPIO_MODE_OUTPUT_PP;g.Pull=GPIO_NOPULL;g.Speed=GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_WritePin(GPIOA,(uint16_t)pa_mask(),GPIO_PIN_RESET);g.Pin=pa_mask();HAL_GPIO_Init(GPIOA,&g);
  HAL_GPIO_WritePin(GPIOB,(uint16_t)pb_mask(),GPIO_PIN_RESET);g.Pin=pb_mask();HAL_GPIO_Init(GPIOB,&g);
}
void mic_load_init(void){
  ld_init(&core);mic_load_request=0;stop_outputs();
  protection=safety_bits();cleanup_done=1;publish_at=HAL_GetTick()-50U;
  for(unsigned i=0;i<3;i++)ccr_min[i]=UINT32_MAX;
}
void mic_load_tim_update(void){
  if(!mic_load_active())return;
  uint32_t now=DWT->CYCCNT,bad=guard();
  stop_outputs();
  if(!ld_tick(&core,now,bad))return;
  if(updates){uint32_t gap=now-tim_previous;if(gap>tim_max_gap)tim_max_gap=gap;}
  tim_previous=now;
  ACIM_VF_CalcAngle(&replay);
  uint16_t rc=ACIM_VF_Controller(&replay);
  if(rc){(void)ld_tick(&core,DWT->CYCCNT,LD_MATH);return;}
  ++updates;
  uint32_t ccr[3]={TIM1->CCR1,TIM1->CCR2,TIM1->CCR3};
  for(unsigned i=0;i<3;i++){if(ccr[i]<ccr_min[i])ccr_min[i]=ccr[i];if(ccr[i]>ccr_max[i])ccr_max[i]=ccr[i];}
  uint32_t cost=DWT->CYCCNT-now;if(cost>tim_max_cycles)tim_max_cycles=cost;
}
void mic_load_medium_update(void){
  if(!mic_load_active())return;
  uint32_t now=DWT->CYCCNT;
  if(!ld_tick(&core,now,guard()))return;
  (void)ACIM_VF_FluxFreqCalc(&replay);++medium_updates;
}
void mic_load_adc_enter(uint32_t now){
  adc_at=now;++adc_seen;
  if(mic_load_active()){
    if(adc_calls){uint32_t gap=now-adc_previous;if(gap>adc_max_gap)adc_max_gap=gap;}
    adc_previous=now;adc_begin=now;++adc_calls;
  }
}
void mic_load_adc_exit(uint32_t now,uint32_t good){
  if(mic_load_active()){
    uint32_t cost=now-adc_begin;if(cost>adc_max_cycles)adc_max_cycles=cost;
    adc_accepted+=good?1U:0U;
  }
}
static void publish(void){
  uint32_t r[LD_REPORT_WORDS]={0};
  r[0]=LD_MAGIC;r[1]=1;r[2]=LD_BUILD;r[3]=LD_REPORT_WORDS;
  r[5]=core.state;r[6]=core.reason;r[7]=core.attempted;r[8]=core.start;
  r[9]=core.stop;r[10]=core.elapsed;r[11]=SystemCoreClock;r[12]=updates;
  r[13]=adc_calls;r[14]=adc_accepted;r[15]=tim_max_cycles;r[16]=adc_max_cycles;
  r[17]=tim_max_gap;r[18]=adc_max_gap;r[19]=poll_max_gap;
  for(unsigned i=0;i<3;i++){r[20+2*i]=ccr_min[i];r[21+2*i]=ccr_max[i];}
  r[26]=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  r[27]=327U; /* Only the private computation replay, never actual Vbus. */
  r[28]=TIM1->BDTR;r[29]=TIM1->CR1;r[30]=TIM1->DIER;r[31]=TIM1->ARR;
  r[32]=TIM1->CCR1;r[33]=TIM1->CCR2;r[34]=TIM1->CCR3;r[35]=TIM1->CCR4;
  r[36]=MC_GetCurrentFaultsMotor1();r[37]=MC_GetOccurredFaultsMotor1();
  r[38]=pins_low()?1U:0U;r[39]=cached_bad;r[40]=mic_local_stop_latched;
  mic_encoder_load_snapshot(&r[41]); /* 17 words, real encoder state. */
  r[58]=mic_current_load_quality();r[59]=adc_seen;r[60]=core.limit;
  r[61]=medium_updates;r[62]=3000;r[63]=(uint32_t)(replay.fFlux_Freq_Hz*1000.0f);
  r[64]=replay_ramp.FrequencyHz;r[65]=(uint32_t)replay.fCalcAngleExecFreqHz;
  r[66]=guard_adc_stamp;r[67]=guard_cache_stamp;r[68]=guard_clock;
  seq+=2;r[4]=seq;r[69]=seq;r[70]=ld_crc(r+5,64);r[71]=0x4c44454eU;
  mic_load_report[4]=seq|1U;__DMB();
  for(unsigned i=0;i<LD_REPORT_WORDS;i++)if(i!=4)mic_load_report[i]=r[i];
  __DMB();mic_load_report[4]=seq;
}
void mic_load_poll(void){
  uint32_t now=DWT->CYCCNT;
  if(poll_previous){uint32_t gap=now-poll_previous;if(gap>poll_max_gap)poll_max_gap=gap;}
  poll_previous=now;
  uint32_t bus=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  uint32_t bad=bus>=20U?LD_BUS:0;
  if(!pins_low() || !(TIM1->BDTR&TIM_BDTR_BKE))bad|=LD_CONFIG;
  if(mic_local_stop_blocked())bad|=LD_LOCAL_STOP;
  cached_bad=bad;cached_at=now;
  if(mic_load_request){
    uint32_t request=mic_load_request;mic_load_request=0;
    if(request==LD_CANCEL){if(mic_load_active())(void)ld_tick(&core,now,LD_COMMAND);}
    else if(!core.attempted){
      if(request!=LD_REQUEST)bad|=LD_COMMAND;
      bad|=guard();
      ld_core candidate;ld_init(&candidate);
      if(ld_request(&candidate,now,SystemCoreClock,bad)){
        replay=*pACIM_VF_Component_M1;
        replay.fFlux_Freq_Hz=0;replay.fFlux_Freq_rads=0;replay.fFlux_Angle_rad=0;
        /* Same Vbus/2 normalization and private MCSDK500Hz/3000ms ramp. */
        replay.fVoutMax_PWM_Mod_V=327.0f/2.0f;
        replay_ramp=*replay.pRMNGR;replay.pRMNGR=&replay_ramp;
        REMNG_Init(&replay_ramp);
        if(!ACIM_VF_ExecRamp(&replay,50,3000U)){
          core.reason=LD_MATH;core.attempted=1;core.state=LD_DENIED;return;
        }
        saved_ccr[0]=TIM1->CCR1;saved_ccr[1]=TIM1->CCR2;saved_ccr[2]=TIM1->CCR3;saved_ccr[3]=TIM1->CCR4;
        cleanup_done=0;stop_outputs();LL_TIM_ClearFlag_UPDATE(TIM1);
        /* Publish RUN last; an ADC/TIM IRQ cannot see an uninitialized copy. */
        core.reason=candidate.reason;core.attempted=candidate.attempted;core.start=candidate.start;
        core.stop=0;core.elapsed=0;core.limit=candidate.limit;core.hz=candidate.hz;
        __DMB();core.state=LD_RUNNING;LL_TIM_EnableIT_UPDATE(TIM1);
      }else{
        core.reason=candidate.reason;core.attempted=candidate.attempted;core.hz=candidate.hz;
        __DMB();core.state=candidate.state;
      }
    }
  }
  if(mic_load_active()){
    uint32_t all=guard();stop_outputs();
    if(ld_tick(&core,DWT->CYCCNT,all))LL_TIM_EnableIT_UPDATE(TIM1);
  }
  if(!mic_load_active()&&!cleanup_done){
    stop_outputs();LL_TIM_DisableIT_UPDATE(TIM1);
    TIM1->CCR1=saved_ccr[0];TIM1->CCR2=saved_ccr[1];TIM1->CCR3=saved_ccr[2];TIM1->CCR4=saved_ccr[3];
    cleanup_done=1;
  }
  uint32_t ms=HAL_GetTick();
  if((uint32_t)(ms-publish_at)>=50U){publish_at=ms;publish();}
}
