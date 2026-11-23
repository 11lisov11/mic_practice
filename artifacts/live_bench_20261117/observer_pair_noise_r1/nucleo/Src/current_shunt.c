#include "main.h"
#include "mc_config.h"
#include "current_shunt.h"
#include "multi_native.h"
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths);
#define CM_ZERO_REPORT(s,mean,var,paths) mic_zero_record((s)->zero_attempts,(s)->zero_stable,(s)->zero_last_bad,mean,(s)->zero_low,(s)->zero_high,var,paths)
#include "current_core.h"
#include "peak_core.h"
#include "current_adc_window_plan.h"
#include "current_adc_deadline.h"
#include "parameters_conversion.h"
#include "uart_v3_transport.h"
#include "noise_core.h"
#include "stm32g4xx_ll_adc.h"
#include "stm32g4xx_ll_tim.h"
#include <math.h>

/* Monitoring only: this module never writes CCR1..3, CCER, MOE, BKIN,
 * motor commands, calibration files, or the current/flux regulators. */
enum { CM_BEFORE_TOP=128U, CM_IDLE_BEFORE_TOP=384U, CM_SETTLE_TICKS=TW_AFTER+TNOISE+32U, CM_ACQUIRE_TICKS=112U };
static cm_core state;
static volatile uint32_t state_sequence;
#include "current_snapshot.h"
static nd_state idle_noise;
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
/* Pack only private ISR flags to make room for a full32-bit context epoch.
 * The public cm_core layout and trace wire remain byte-for-byte unchanged. */
static struct {
  uint8_t pair:2,valid:1,active:1,init:1,lost:1;
} adc_flags;
typedef char adc_flags_must_be_one_byte[(sizeof(adc_flags)==1)?1:-1];
#define pending_pair adc_flags.pair
#define pending_valid adc_flags.valid
#define pending_active adc_flags.active
#define initialized adc_flags.init
#define lost_sync adc_flags.lost
static uint32_t pending_epoch;
static uint32_t packets;

static pc_capture peak;
static volatile uint32_t peak_epoch;
static volatile uint16_t peak_active_ccr[4],peak_update_cnt,peak_update_cr1;
static uint8_t peak_sealed;
/* Foreground only requests; ADC IRQ remains sole writer of raw capture. */
static volatile uint8_t peak_observer_request;
void mic_current_request_observer_capture(void){peak_observer_request=1;}


static volatile ma_current_sample ma_fast_sample;
int mic_current_fast(ma_current_sample*out){
 uint32_t seq=ma_fast_sample.sequence;__DMB();
 out->sequence=seq;out->cycles=ma_fast_sample.cycles;out->epoch=ma_fast_sample.epoch;
 out->pair=ma_fast_sample.pair;out->reserved=0;
 out->valid=ma_fast_sample.valid;out->zero=ma_fast_sample.zero;
 out->arr=ma_fast_sample.arr;out->bus_v=ma_fast_sample.bus_v;
 for(unsigned i=0;i<3;i++)out->ccr[i]=ma_fast_sample.ccr[i];
 for(unsigned i=0;i<3;i++)out->counts[i]=ma_fast_sample.counts[i];
 __DMB();
 return !(seq&1)&&seq==ma_fast_sample.sequence;
}
static void ma_publish_current(uint32_t cycles,uint32_t epoch,uint8_t eligible,uint8_t pair,uint16_t a,uint16_t b,const uint16_t*ccr,uint16_t bus){
 ++ma_fast_sample.sequence;__DMB();ma_fast_sample.cycles=cycles;ma_fast_sample.epoch=epoch;
 ma_fast_sample.valid=(uint8_t)(eligible&&state.zero_ready&&a>=16&&b>=16&&a<=4079&&b<=4079);
 ma_fast_sample.pair=pair;ma_fast_sample.reserved=0;
 ma_fast_sample.zero=state.zero_ready;ma_fast_sample.arr=(uint16_t)TIM1->ARR;ma_fast_sample.bus_v=bus;
 for(unsigned i=0;i<3;i++)ma_fast_sample.ccr[i]=ccr[i];
  int16_t counts[3]={0,0,0};
  if(!cm_reconstruct(&state,pair,a,b,counts))ma_fast_sample.valid=0;
  for(unsigned i=0;i<3;i++)ma_fast_sample.counts[i]=counts[i];
 __DMB();++ma_fast_sample.sequence;
}

void mic_current_update_epoch(void) {
  peak_active_ccr[0]=(uint16_t)TIM1->CCR1;
  peak_active_ccr[1]=(uint16_t)TIM1->CCR2;
  peak_active_ccr[2]=(uint16_t)TIM1->CCR3;
  peak_active_ccr[3]=(uint16_t)TIM1->CCR4;
  peak_update_cnt=(uint16_t)TIM1->CNT;peak_update_cr1=(uint16_t)TIM1->CR1;
  ++peak_epoch;
}


/* ADC-IRQ tail only. Middle of down-count half: injection has finished,
 * and>1024 ticks remain before bottom/TIM1 preemption. A regular47.5+12.5
 * ADC-cycle conversion at42.5MHz needs240 timer ticks. */
uint8_t mic_current_regular_window(void){
 uint32_t cnt=TIM1->CNT,down=TIM1->CR1&TIM_CR1_DIR;
 uint32_t arr=TIM1->ARR;
 return (uint8_t)(down&&arr>1536U&&cnt>1024U&&cnt<arr-512U);
}

static void queue_pair(uint8_t pair) {
  const uint32_t trigger=LL_ADC_INJ_TRIG_EXT_TIM1_TRGO|LL_ADC_INJ_TRIG_EXT_RISING;
  ADC1->JSQR=trigger|((uint32_t)(pair>=2?7U:1U)<<ADC_JSQR_JSQ1_Pos);
  ADC2->JSQR=trigger|((uint32_t)((pair==0||pair==3)?7U:6U)<<ADC_JSQR_JSQ1_Pos);
  pending_pair=pair;
}

void mic_current_init(void) {
  state_sequence=0;cm_init(&state);nd_init(&idle_noise);pc_init(&peak);memset(zero_history,0,sizeof(zero_history));
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
  LL_TIM_OC_SetCompareCH4(TIM1,TIM1->ARR-CM_IDLE_BEFORE_TOP);
  LL_TIM_SetTriggerOutput(TIM1,LL_TIM_TRGO_OC4REF);
  pending_epoch=peak_epoch+1U;
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
  /* The apex is NOT the update deadline. Check time until bottom UEV. */
  uint8_t early=(uint8_t)mic_adc_publish_in_time(TIM1->ARR,count,direction,old_trigger);
  uint32_t isr1=ADC1->ISR,isr2=ADC2->ISR,jsqr1=0,jsqr2=0;
  /* JQM=1 must be EMPTY after this single injected sequence. */
  jsqr1=ADC1->JSQR;jsqr2=ADC2->JSQR;
  uint8_t both=(uint8_t)LL_ADC_IsActiveFlag_JEOS(ADC2);
  if(!both || ((isr1|isr2)&ADC_ISR_JQOVF) || jsqr1 || jsqr2)lost_sync=1;
  uint16_t a=(uint16_t)(ADC1->JDR1>>4),b=(uint16_t)(ADC2->JDR1>>4);
  LL_ADC_ClearFlag_JEOS(ADC1);LL_ADC_ClearFlag_JEOS(ADC2);
  uint8_t active=(uint8_t)(LL_TIM_IsEnabledAllOutputs(TIM1)!=0);
  uint16_t bus=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  uint8_t captured_pair=pending_pair,valid0=pending_valid,active0=pending_active;
  uint8_t stamp_ok=(uint8_t)(pending_epoch==epoch0);
  uint8_t bottom_ok=(uint8_t)mic_adc_bottom_update(TIM1->ARR,current_update_cnt,current_update_cr1&TIM_CR1_DIR);
  uint8_t context_ok=(uint8_t)(epoch0==epoch1 && epoch1==peak_epoch &&
      current_ccr[3]==old_trigger && stamp_ok && bottom_ok);
  uint8_t geometry_ok=(uint8_t)mic_current_window_safe(captured_pair,
      current_ccr[0],current_ccr[1],current_ccr[2],current_ccr[3],
      CM_SETTLE_TICKS,CM_ACQUIRE_TICKS);
  /* Raw trigger eligibility is deliberately independent of geometry: retain
   * an invalid-window spike as evidence, but NEVER include it in RMS/peak. */
  uint8_t raw_eligible=(uint8_t)(both && !lost_sync && context_ok &&
      active0 && active && state.zero_ready);
  uint8_t eligible=(uint8_t)(raw_eligible && valid0 && geometry_ok);
  uint8_t pair=active?cm_choose_pair(u,v,w):(pending_pair==0?2:0);
  int noise_next=nd_step(&idle_noise,captured_pair,a,b,!active,bus<=20U,state.zero_ready,
    both&&!lost_sync&&!jsqr1&&!jsqr2,cycles0);
  if(!active && noise_next>=0)pair=(uint8_t)noise_next;
  mic_current_window_plan plan=mic_plan_current_window(u,v,w,
      TIM1->ARR-CM_BEFORE_TOP,CM_SETTLE_TICKS,CM_ACQUIRE_TICKS);
  if(!active){plan.trigger=TIM1->ARR-CM_IDLE_BEFORE_TOP;plan.valid=1;}
  else pair=plan.pair;
  /* Even if no safe interval exists, keep ADC heartbeat at the bounded latest
   * point and explicitly invalidate the following measurement. */
  if(!plan.valid)plan.trigger=TIM1->ARR-CM_BEFORE_TOP;
  LL_TIM_OC_SetCompareCH4(TIM1,plan.trigger);
  pending_valid=(uint8_t)(early && plan.valid && bottom_ok && epoch0==peak_epoch);
  pending_active=active;
  pending_epoch=epoch0+1U;
  queue_pair(pair);
  uint16_t queue_cnt=(uint16_t)TIM1->CNT,queue_dir=(uint16_t)(TIM1->CR1&TIM_CR1_DIR);
  uint32_t queue_cycles=DWT->CYCCNT-cycles0;
  if(epoch0!=peak_epoch)pending_valid=0;
  /* Publish next context before zero statistics and diagnostic work. */
  if(captured_pair<3){
    ++state_sequence;__DMB();
    cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,
            bus<=20U && both && !lost_sync && early && !active);
    __DMB();++state_sequence;
  }
  ma_publish_current(cycles0,epoch0,eligible,captured_pair,a,b,current_ccr,bus);
  /* With MOE off MCSDK may mask UPDATE IRQ. Autonull needs the freshly
   * completed single mux context (JQM empty), not an unserviced UEV stamp.
   * Its500ms settling and unchanged three-block/statistical gates stay in core. */
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
        (!geometry_ok?1024:0)|(!early?2048:0)|(!stamp_ok?4096:0)|((jsqr1||jsqr2)?8192:0));
    int32_t ia=(int32_t)state.offset[cm_path1(captured_pair)]-a;
    int32_t ib=(int32_t)state.offset[cm_path2(captured_pair)]-b,ic=-ia-ib;
    uint32_t mag=(uint32_t)(ia<0?-ia:ia),m=(uint32_t)(ib<0?-ib:ib);
    if(m>mag)mag=m;
    m=(uint32_t)(ic<0?-ic:ic);
    if(m>mag)mag=m;
    if(peak_observer_request){peak_observer_request=0;pc_request_observer(&peak);}
    pc_push(&peak,&sample,HAL_GetTick(),active,raw_eligible,mag);
  }
}

static uint16_t ma_u(float x,uint8_t *flags) {
  if(!isfinite(x)||x<0.0f||x>65534.0f){*flags|=CM_CLIP;return 65535;}
  return (uint16_t)(x+0.5f);
}
static void put16(uint8_t *p,uint16_t x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static void put32(uint8_t *p,uint32_t x){for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(x>>(8*i));}

uint8_t mic_current_packet(uint8_t *packet,uint8_t detail,uint32_t build) {
  cm_core copy;
  if(!cm_snapshot_read(&copy,&state,&state_sequence))return 0;
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
  packet[3]=flags;packet[38]=1;uv3_seal(packet);return 1;
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

/* Main/OFF-only export of a separate diagnostic buffer. It never touches the
 * frozen motor-current trace, the SD snapshot, the ID result or zero history. */
uint8_t mic_current_noise_packet(uint8_t*packet,uint8_t page,uint32_t build){
 if(LL_TIM_IsEnabledAllOutputs(TIM1)||page>=ND_PAGES||!idle_noise.done)return 0;
 if(!idle_noise.ready){
  uint32_t registers[8]={ADC1->SMPR1,ADC1->SMPR2,ADC2->SMPR1,ADC2->SMPR2,
   ADC12_COMMON->CCR,ADC1->CFGR,ADC2->CFGR,TIM1->CCR4};
  (void)nd_seal(&idle_noise,build,SystemCoreClock,DBGMCU->IDCODE,registers);
 }
 memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=0xE7;
 packet[3]=1;packet[4]=page;packet[5]=ND_PAGES;put32(packet+6,build);put32(packet+10,idle_noise.crc);
 unsigned offset=page*24U,n=ND_BYTES-offset;if(n>24)n=24;
 memcpy(packet+14,idle_noise.bytes+offset,n);uv3_seal(packet);return 1;
}
