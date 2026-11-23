#include "main.h"
#include "mc_config.h"
#include "current_shunt.h"
#include "current_core.h"
#include "parameters_conversion.h"
#include "uart_v3_transport.h"
#include "stm32g4xx_ll_adc.h"
#include "stm32g4xx_ll_tim.h"
#include <math.h>

/* Monitoring only: this module never writes CCR1..3, CCER, MOE, BKIN,
 * motor commands, calibration files, or the current/flux regulators. */
enum { CM_BEFORE_TOP=384U, CM_SETTLE_TICKS=TW_AFTER+TNOISE+32U };
static cm_core state;
static uint8_t pending_pair,pending_valid,pending_active,initialized,lost_sync;
static uint32_t packets;

static void queue_pair(uint8_t pair) {
  const uint32_t trigger=LL_ADC_INJ_TRIG_EXT_TIM1_TRGO|LL_ADC_INJ_TRIG_EXT_RISING;
  ADC1->JSQR=trigger|((uint32_t)(pair==2?7U:1U)<<ADC_JSQR_JSQ1_Pos);
  ADC2->JSQR=trigger|((uint32_t)(pair==0?7U:6U)<<ADC_JSQR_JSQ1_Pos);
  pending_pair=pair;
}

void mic_current_init(void) {
  cm_init(&state);
  LL_ADC_DisableIT_JEOS(ADC1);LL_ADC_DisableIT_JEOS(ADC2);
  LL_ADC_INJ_StopConversion(ADC1);LL_ADC_INJ_StopConversion(ADC2);
  /* Bounded initialization only; no blocking wait in an IRQ. */
  uint32_t deadline=HAL_GetTick()+5U;
  while(LL_ADC_INJ_IsStopConversionOngoing(ADC1)||LL_ADC_INJ_IsStopConversionOngoing(ADC2))
    if((int32_t)(HAL_GetTick()-deadline)>=0)return;
  LL_ADC_INJ_SetQueueMode(ADC1,LL_ADC_INJ_QUEUE_2CONTEXTS_END_EMPTY);
  LL_ADC_INJ_SetQueueMode(ADC2,LL_ADC_INJ_QUEUE_2CONTEXTS_END_EMPTY);
  LL_ADC_ClearFlag_JEOS(ADC1);LL_ADC_ClearFlag_JEOS(ADC2);
  /* Keep all power PWM/deadtime registers intact. Only ADC strobe CH4 moves
   * ahead of the apex to allow both conversions before the next update. */
  LL_TIM_OC_SetCompareCH4(TIM1,TIM1->ARR-CM_BEFORE_TOP);
  LL_TIM_SetTriggerOutput(TIM1,LL_TIM_TRGO_OC4REF);
  queue_pair(0);pending_valid=0;pending_active=0;initialized=1;
  LL_ADC_EnableIT_JEOS(ADC1);
  LL_ADC_INJ_StartConversion(ADC1);LL_ADC_INJ_StartConversion(ADC2);
}

void mic_current_adc_irq(void) {
  if(!initialized || !LL_ADC_IsActiveFlag_JEOS(ADC1))return;
  /* Capture next-cycle shadows BEFORE calculation and before a possible
   * apex update. If IRQ latency crosses the apex, invalidate the next pair. */
  uint32_t u=TIM1->CCR1,v=TIM1->CCR2,w=TIM1->CCR3;
  uint32_t count=TIM1->CNT,direction=TIM1->CR1&TIM_CR1_DIR;
  uint8_t early=!direction && count>=TIM1->CCR4 && count<TIM1->ARR-24U;
  uint8_t both=(uint8_t)LL_ADC_IsActiveFlag_JEOS(ADC2);
  if(!both)lost_sync=1; /* never combine a prior ADC2 conversion with ADC1 */
  uint16_t a=(uint16_t)(ADC1->JDR1>>4),b=(uint16_t)(ADC2->JDR1>>4);
  LL_ADC_ClearFlag_JEOS(ADC1);LL_ADC_ClearFlag_JEOS(ADC2);
  uint8_t active=(uint8_t)(LL_TIM_IsEnabledAllOutputs(TIM1)!=0);
  uint16_t bus=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  cm_sample(&state,HAL_GetTick(),active,pending_pair,a,b,
            both && !lost_sync && pending_valid && pending_active && active,
            bus<=20U && both && !lost_sync && early);
  uint8_t pair=active?cm_choose_pair(u,v,w):(pending_pair==0?2:0);
  pending_valid=early && cm_pair_window(pair,u,v,w,TIM1->CCR4,CM_SETTLE_TICKS);
  pending_active=active;
  queue_pair(pair);
}

static uint16_t ma_u(float x,uint8_t *flags) {
  if(!isfinite(x)||x<0.0f||x>65534.0f){*flags|=CM_CLIP;return 65535;}
  return (uint16_t)(x+0.5f);
}
static void put16(uint8_t *p,uint16_t x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static void put32(uint8_t *p,uint32_t x){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(x>>(8*i));}

void mic_current_packet(uint8_t *packet,uint8_t detail,uint32_t build) {
  cm_core copy;
  uint32_t key=__get_PRIMASK();__disable_irq();copy=state;__set_PRIMASK(key);
  memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=detail==2?0xD7:detail?0xD6:0xD5;
  uint8_t flags=(copy.zero_ready?CM_ZERO:0)|(copy.zero_bad?CM_ZERO_BAD:0);
  if(copy.was_active)flags|=CM_ACTIVE;
  cm_window *w=&copy.published;
  if(w->flags&CM_FROZEN)flags|=CM_FROZEN;
  flags|=w->flags&(CM_CLIP|CM_TIMING);
  if(copy.zero_ready && cm_window_valid(w))flags|=CM_VALID;
  packet[4]=(uint8_t)++packets;
  put32(packet+6,build);
  put32(packet+10,detail?HAL_GetTick():w->end_ms);
  if(detail==2) {
    for(unsigned i=0;i<4;++i){put16(packet+14+2*i,copy.zero_low[i]);put16(packet+22+2*i,copy.zero_high[i]);}
    packet[5]=copy.zero_attempts;packet[30]=copy.zero_stable;packet[31]=copy.zero_last_bad;
    packet[32]=CM_ZERO_BLOCKS;packet[33]=CM_ZERO_MAX_BLOCKS;packet[34]=CM_ZERO_SPAN;packet[35]=CM_ZERO_DRIFT;
  } else if(detail) {
    for(unsigned i=0;i<4;++i){put16(packet+14+2*i,copy.raw[i]);put16(packet+22+2*i,copy.offset[i]);put16(packet+30+2*i,copy.count[i]);}
    packet[5]=4;
  } else {
    const float scale=1000.0f*ADC_REFERENCE_VOLTAGE/(4095.0f*RSHUNT*AMPLIFICATION_GAIN);
    for(unsigned i=0;i<3;++i) {
      put16(packet+14+2*i,ma_u(w->n?sqrtf((float)w->square[i]/w->n)*scale:0,&flags));
      put16(packet+20+2*i,ma_u(w->peak[i]*scale,&flags));
      float instant=w->last[i]*scale;
      if(instant>32767||instant< -32767){flags|=CM_CLIP;instant=0;}
      put16(packet+26+2*i,(uint16_t)(int16_t)instant);
    }
    if(flags&CM_CLIP)flags&=(uint8_t)~CM_VALID;
    packet[5]=(uint8_t)((w->n+w->bad)?100U*w->n/(w->n+w->bad):0);
    packet[32]=w->reconstructed;
    put16(packet+34,(uint16_t)(w->end_ms-w->start_ms));
    put16(packet+36,(uint16_t)(w->bad>65535?65535:w->bad));
  }
  packet[3]=flags;packet[38]=1;uv3_seal(packet);
}
