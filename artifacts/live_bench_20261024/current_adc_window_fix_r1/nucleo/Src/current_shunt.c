#include "main.h"
#include "mc_config.h"
#include "current_shunt.h"
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths);
#define CM_ZERO_REPORT(s,mean,var,paths) mic_zero_record((s)->zero_attempts,(s)->zero_stable,(s)->zero_last_bad,mean,(s)->zero_low,(s)->zero_high,var,paths)
#include "current_core.h"
#include "peak_core.h"
#include "current_adc_window_plan.h"
#include "parameters_conversion.h"
#include "uart_v3_transport.h"
#include "stm32g4xx_ll_adc.h"
#include "stm32g4xx_ll_tim.h"
#include <math.h>

/* Monitoring only: this module never writes CCR1..3, CCER, MOE, BKIN,
 * motor commands, calibration files, or the current/flux regulators. */
enum { CM_BEFORE_TOP=384U, CM_SETTLE_TICKS=TW_AFTER+TNOISE+32U, CM_ACQUIRE_TICKS=112U };
static cm_core state;
typedef struct { uint8_t bytes[15]; } zh_block;
typedef char zh_block_must_be_15[(sizeof(zh_block)==15)?1:-1];
static zh_block zero_history[8];
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths) {
 if(attempt<1 || attempt>8)return;
 uint8_t *b=zero_history[attempt-1U].bytes;
 for(unsigned i=0;i<4;++i){
   b[2*i]=(uint8_t)mean[i];b[2*i+1]=(uint8_t)(mean[i]>>8);
   unsigned span=high[i]-low[i];b[8+i]=(uint8_t)(span>255U?255U:span);
   if(span>255U)paths|=16U<<i;
 }
 b[12]=(uint8_t)((stable&3U)|(rejected<<2));b[13]=(uint8_t)variance_q7;b[14]=(uint8_t)paths;
}
static uint8_t pending_pair,pending_valid,pending_active,initialized,lost_sync;
static uint32_t packets;

static pc_capture peak;
static volatile uint32_t peak_epoch;
static volatile uint16_t peak_active_ccr[4],peak_update_cnt,peak_update_cr1;
static uint8_t peak_sealed;

void mic_current_update_epoch(void) {
  peak_active_ccr[0]=(uint16_t)TIM1->CCR1;
  peak_active_ccr[1]=(uint16_t)TIM1->CCR2;
  peak_active_ccr[2]=(uint16_t)TIM1->CCR3;
  peak_active_ccr[3]=(uint16_t)TIM1->CCR4;
  peak_update_cnt=(uint16_t)TIM1->CNT;peak_update_cr1=(uint16_t)TIM1->CR1;
  ++peak_epoch;
}


static void queue_pair(uint8_t pair) {
  const uint32_t trigger=LL_ADC_INJ_TRIG_EXT_TIM1_TRGO|LL_ADC_INJ_TRIG_EXT_RISING;
  ADC1->JSQR=trigger|((uint32_t)(pair==2?7U:1U)<<ADC_JSQR_JSQ1_Pos);
  ADC2->JSQR=trigger|((uint32_t)(pair==0?7U:6U)<<ADC_JSQR_JSQ1_Pos);
  pending_pair=pair;
}

void mic_current_init(void) {
  cm_init(&state);pc_init(&peak);memset(zero_history,0,sizeof(zero_history));
  CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;
  DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;
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
  LL_TIM_OC_EnablePreload(TIM1,LL_TIM_CHANNEL_CH4);
  LL_TIM_OC_SetCompareCH4(TIM1,TIM1->ARR-CM_BEFORE_TOP);
  LL_TIM_SetTriggerOutput(TIM1,LL_TIM_TRGO_OC4REF);
  queue_pair(0);pending_valid=0;pending_active=0;initialized=1;
  LL_ADC_EnableIT_JEOS(ADC1);
  LL_ADC_INJ_StartConversion(ADC1);LL_ADC_INJ_StartConversion(ADC2);
}

void mic_current_adc_irq(void) {
  if(!initialized || !LL_ADC_IsActiveFlag_JEOS(ADC1))return;
  /* Bind the completed sample to one update epoch BEFORE changing shadows.
   * UPDATE latches all CCRs, then the VF task writes the following cycle.
   * OC4 preload is mandatory: changing a shadow must not create a trigger now. */
  uint32_t epoch0=peak_epoch,cycles0=DWT->CYCCNT;
  uint16_t current_ccr[4];
  for(unsigned i=0;i<4;++i)current_ccr[i]=peak_active_ccr[i];
  uint16_t current_update_cnt=peak_update_cnt,current_update_cr1=peak_update_cr1;
  uint32_t epoch1=peak_epoch;
  uint32_t u=TIM1->CCR1,v=TIM1->CCR2,w=TIM1->CCR3,old_trigger=TIM1->CCR4;
  uint32_t count=TIM1->CNT,direction=TIM1->CR1&TIM_CR1_DIR;
  uint8_t early=(uint8_t)(!direction && count>=old_trigger && count<TIM1->ARR-24U);
  uint32_t isr1=ADC1->ISR,isr2=ADC2->ISR,jsqr1=0,jsqr2=0;
  if(!peak.frozen){jsqr1=ADC1->JSQR;jsqr2=ADC2->JSQR;}
  uint8_t both=(uint8_t)LL_ADC_IsActiveFlag_JEOS(ADC2);
  if(!both || ((isr1|isr2)&ADC_ISR_JQOVF))lost_sync=1;
  uint16_t a=(uint16_t)(ADC1->JDR1>>4),b=(uint16_t)(ADC2->JDR1>>4);
  LL_ADC_ClearFlag_JEOS(ADC1);LL_ADC_ClearFlag_JEOS(ADC2);
  uint8_t active=(uint8_t)(LL_TIM_IsEnabledAllOutputs(TIM1)!=0);
  uint16_t bus=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  uint8_t captured_pair=pending_pair,valid0=pending_valid,active0=pending_active;
  uint8_t context_ok=(uint8_t)(epoch0==epoch1 && epoch1==peak_epoch &&
      current_ccr[3]==old_trigger);
  uint8_t geometry_ok=(uint8_t)mic_current_window_safe(captured_pair,
      current_ccr[0],current_ccr[1],current_ccr[2],current_ccr[3],
      CM_SETTLE_TICKS,CM_ACQUIRE_TICKS);
  /* Raw trigger eligibility is deliberately independent of geometry: retain
   * an invalid-window spike as evidence, but NEVER include it in RMS/peak. */
  uint8_t raw_eligible=(uint8_t)(both && !lost_sync && context_ok &&
      active0 && active && state.zero_ready);
  uint8_t eligible=(uint8_t)(raw_eligible && valid0 && geometry_ok);
  uint8_t pair=active?cm_choose_pair(u,v,w):(pending_pair==0?2:0);
  mic_current_window_plan plan=mic_plan_current_window(u,v,w,
      TIM1->ARR-CM_BEFORE_TOP,CM_SETTLE_TICKS,CM_ACQUIRE_TICKS);
  if(!active){plan.trigger=TIM1->ARR-CM_BEFORE_TOP;plan.valid=1;}
  else pair=plan.pair;
  /* Even if no safe interval exists, keep ADC heartbeat at the bounded latest
   * point and explicitly invalidate the following measurement. */
  if(!plan.valid)plan.trigger=TIM1->ARR-CM_BEFORE_TOP;
  LL_TIM_OC_SetCompareCH4(TIM1,plan.trigger);
  pending_valid=(uint8_t)(early && plan.valid && epoch0==peak_epoch);
  pending_active=active;
  queue_pair(pair);
  uint16_t queue_cnt=(uint16_t)TIM1->CNT,queue_dir=(uint16_t)(TIM1->CR1&TIM_CR1_DIR);
  uint32_t queue_cycles=DWT->CYCCNT-cycles0;
  if(epoch0!=peak_epoch)pending_valid=0;
  /* Publish next context before zero statistics and diagnostic work. */
  cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,
            bus<=20U && both && !lost_sync && early && context_ok);
  if(!peak.frozen && (active || peak.running)) {
    if(queue_cycles>peak.blob.header.reserved)peak.blob.header.reserved=queue_cycles;
    pc_sample sample={0};
    sample.cycles=cycles0;sample.epoch_before=epoch0;sample.epoch_after=epoch1;
    sample.isr1=isr1;sample.isr2=isr2;sample.jsqr1=jsqr1;sample.jsqr2=jsqr2;
    for(unsigned i=0;i<4;++i){sample.active_ccr[i]=current_ccr[i];sample.offset[i]=state.offset[i];}
    sample.update_cnt=current_update_cnt;sample.update_cr1=current_update_cr1;
    sample.preload_ccr[0]=(uint16_t)u;sample.preload_ccr[1]=(uint16_t)v;
    sample.preload_ccr[2]=(uint16_t)w;sample.preload_ccr[3]=(uint16_t)plan.trigger;
    sample.cnt=(uint16_t)count;sample.arr=(uint16_t)TIM1->ARR;sample.cr1=(uint16_t)direction;
    sample.raw[0]=a;sample.raw[1]=b;sample.pair=captured_pair;sample.next_pair=pair;
    sample.cnt_exit=queue_cnt;sample.bus_v=bus;
    sample.reference_deci_hz=(uint16_t)(pACIM_VF_Component_M1->fFlux_Freq_Hz*10.0f);
    uint8_t accepted=(uint8_t)(eligible && a>=16 && b>=16 && a<=4079 && b<=4079);
    sample.flags=(uint16_t)((active?1:0)|(valid0?2:0)|(active0?4:0)|(both?8:0)|
        (lost_sync?16:0)|(early?32:0)|(accepted?64:0)|(!context_ok?128:0)|
        (((isr1|isr2)&ADC_ISR_JQOVF)?256:0)|(queue_dir?512:0)|
        (!geometry_ok?1024:0));
    int32_t ia=(int32_t)state.offset[cm_path1(captured_pair)]-a;
    int32_t ib=(int32_t)state.offset[cm_path2(captured_pair)]-b,ic=-ia-ib;
    uint32_t mag=(uint32_t)(ia<0?-ia:ia),m=(uint32_t)(ib<0?-ib:ib);
    if(m>mag)mag=m;
    m=(uint32_t)(ic<0?-ic:ic);
    if(m>mag)mag=m;
    pc_push(&peak,&sample,HAL_GetTick(),active,raw_eligible,mag);
  }
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
    packet[32]=CM_ZERO_BLOCKS;packet[33]=CM_ZERO_MAX_BLOCKS;packet[34]=0;packet[35]=CM_ZERO_DRIFT;packet[36]=3;packet[37]=2;
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


uint8_t mic_current_peak_packet(uint8_t *packet,uint8_t page,uint32_t build) {
  if(!peak.frozen || LL_TIM_IsEnabledAllOutputs(TIM1) || page>=35)return 0;
  if(!peak_sealed) {
    peak.blob.header.firmware=build;
    peak.blob.header.crc=pc_crc((const uint8_t *)&peak.blob);
    peak_sealed=1;
  }
  memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=0xd8;
  packet[3]=1;packet[4]=1;packet[5]=page;packet[6]=35;
  uint8_t size=page==34?4:30;packet[7]=size;
  memcpy(packet+8,((const uint8_t *)&peak.blob)+page*30U,size);
  packet[38]=1;uv3_seal(packet);return 1;
}


uint8_t mic_zero_packet(uint8_t *packet,uint32_t build) {
 if(LL_TIM_IsEnabledAllOutputs(TIM1) || (!state.zero_ready && !state.zero_bad))return 0;
 unsigned count=state.zero_attempts;
 if(count<3 || count>8)return 0;
 unsigned page=(packets/4U)%count;
 memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=0xd9;
 packet[3]=1;packet[4]=(uint8_t)page;packet[5]=(uint8_t)count;put32(packet+6,build);
 memcpy(packet+10,&zero_history[page],15);
 packet[30]=3;packet[31]=2;packet[32]=3;packet[33]=8;packet[34]=2;
 packet[35]=128;packet[37]=15;packet[38]=1;uv3_seal(packet);return 1;
}
