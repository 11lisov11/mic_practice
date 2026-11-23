
#include <cstdint>
#include <cstdio>
#include <cstdlib>
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths);
#define CM_ZERO_REPORT(s,mean,var,paths) mic_zero_record((s)->zero_attempts,(s)->zero_stable,(s)->zero_last_bad,mean,(s)->zero_low,(s)->zero_high,var,paths)
#include "current_core.h"
#include "current_adc_window_plan.h"
#include "current_adc_deadline.h"
struct Timer {uint32_t CCR1,CCR2,CCR3,CCR4,CNT,CR1,ARR,BDTR;};
struct Adc {uint32_t JSQR,JDR1,ISR;};
static Timer timer;static Adc adc1,adc2;
#define TIM1 (&timer)
#define ADC1 (&adc1)
#define ADC2 (&adc2)
#define TIM_CR1_DIR 16U
#define ADC_JSQR_JSQ1_Pos 8
#define LL_ADC_INJ_TRIG_EXT_TIM1_TRGO 4U
#define LL_ADC_INJ_TRIG_EXT_RISING 1U
enum {CM_SETTLE_TICKS=771,CM_BEFORE_TOP=128,CM_IDLE_BEFORE_TOP=384,CM_ACQUIRE_TICKS=112};
static uint32_t tick;
static uint16_t bus;
static struct {int _Super;} BusVoltageSensor_M1;
static uint32_t HAL_GetTick(){return tick;}
static uint16_t VBS_GetAvBusVoltage_V(int*){return bus;}
static uint32_t LL_TIM_IsEnabledAllOutputs(Timer *t){return t->BDTR&32768;}
static unsigned LL_ADC_IsActiveFlag_JEOS(Adc *a){return a->ISR&1;}
static void LL_ADC_ClearFlag_JEOS(Adc *a){a->ISR&=~1U;}
static unsigned checks;
static void check(bool okay){++checks;if(!okay){fprintf(stderr,"IRQ check %u failed\n",checks);exit(1);}}

static bool diag;static unsigned entered,exited,accepted;
static bool mic_load_active(){return diag;}
static void mic_load_adc_enter(uint32_t){++entered;}
static void mic_load_adc_exit(uint32_t,unsigned good){++exited;accepted+=good?1:0;}
static void LL_TIM_OC_SetCompareCH4(Timer*t,uint32_t v){t->CCR4=v;}

#include "peak_core.h"
#include "peak_wire.h"
struct Dwt {uint32_t CYCCNT;};static Dwt dwt;
#define DWT (&dwt)
#define ADC_ISR_JQOVF 1024U
static struct Vf {float fFlux_Freq_Hz=40;} vf;
static Vf *pACIM_VF_Component_M1=&vf;
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

void mic_current_adc_irq(void) {
  if(!initialized || !LL_ADC_IsActiveFlag_JEOS(ADC1))return;
  mic_load_adc_enter(DWT->CYCCNT);
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
  /* Computational active path only: actual BDTR/MOE is never forged. */
  uint8_t active=(uint8_t)(mic_load_active() || LL_TIM_IsEnabledAllOutputs(TIM1)!=0);
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
  cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,eligible,
            bus<=20U && both && !lost_sync && early && !active);
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
    pc_push(&peak,&sample,HAL_GetTick(),active,raw_eligible,mag);
  }
  mic_load_adc_exit(DWT->CYCCNT,eligible && a>=16 && b>=16 && a<=4079 && b<=4079);
}

uint32_t mic_current_load_quality(void) {
 return (state.zero_ready?1U:0U)|(state.zero_bad?2U:0U)|(lost_sync?4U:0U);
}


#include <cmath>
int main(){
 cm_init(&state);state.zero_ready=1;state.zero_stable=3;state.zero_attempts=3;
 for(unsigned i=0;i<4;++i)state.offset[i]=2067;
 pc_init(&peak);peak_sealed=0;lost_sync=0;initialized=1;
 pending_valid=1;pending_active=0;pending_epoch=1;peak_epoch=0;
 timer={2656,2656,2656,4928,110,0,5312,0};bus=10;
 diag=true;
 for(unsigned n=0;n<80000;n++){
  uint32_t c[4]={timer.CCR1,timer.CCR2,timer.CCR3,timer.CCR4};
  timer.CNT=110;timer.CR1=0;mic_current_update_epoch();
  float angle=6.283185307f*5.0f*n/16000.0f;
  timer.CCR1=unsigned(2655+325*std::sin(angle));
  timer.CCR2=unsigned(2655+325*std::sin(angle+2.0943951f));
  timer.CCR3=unsigned(2655+325*std::sin(angle+4.1887902f));
  tick=1000+n/16;dwt.CYCCNT=n*10625U;
  timer.CNT=c[3]-50;timer.CR1=TIM_CR1_DIR;
  unsigned a=cm_path1(pending_pair),b=cm_path2(pending_pair);
  adc1.JDR1=(state.offset[a]-78)<<4;adc2.JDR1=(state.offset[b]+39)<<4;
  adc1.ISR=adc2.ISR=1;adc1.JSQR=adc2.JSQR=0;
  unsigned before[3]={timer.CCR1,timer.CCR2,timer.CCR3};
  mic_current_adc_irq();
  check(timer.BDTR==0);check(timer.CCR1==before[0]&&timer.CCR2==before[1]&&timer.CCR3==before[2]);
  check(timer.CCR4<=5184&&timer.CCR4>0);
 }
 check(entered==80000&&exited==80000);check(accepted>79000);
 check(state.published.n>1000);check(!lost_sync);check(mic_current_load_quality()==1);
 // Physical pins/MOE stayed OFF while the active timing/reconstruction branch ran.
 check(state.zero_ready&&state.zero_stable==3);check(timer.BDTR==0);check(packets==0);
 printf("{\"passed\":true,\"checks\":%u,\"adc_calls\":%u,\"accepted\":%u,\"actual_target_irq_body\":true,\"physical_MOE\":0}\n",checks,entered,accepted);
}
