
#include <cstdint>
#include <cstdio>
#include <cstdlib>
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths);
#define CM_ZERO_REPORT(s,mean,var,paths) mic_zero_record((s)->zero_attempts,(s)->zero_stable,(s)->zero_last_bad,mean,(s)->zero_low,(s)->zero_high,var,paths)
#include "current_core.h"
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
enum {CM_SETTLE_TICKS=771};
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

#include "peak_core.h"
#include "peak_wire.h"
struct Dwt {uint32_t CYCCNT;};static Dwt dwt;
#define DWT (&dwt)
#define ADC_ISR_JQOVF 1024U
static struct Vf {float fFlux_Freq_Hz=40;} vf;
static Vf *pACIM_VF_Component_M1=&vf;
static cm_core state;
typedef struct {
 uint16_t mean[4],span[4];
 uint8_t status,variance_q7,paths,tick4;
} zh_block;
typedef char zh_block_must_be_20[(sizeof(zh_block)==20)?1:-1];
static zh_block zero_history[8];
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths) {
 if(attempt<1 || attempt>8)return;
 zh_block *b=&zero_history[attempt-1U];
 for(unsigned i=0;i<4;++i){b->mean[i]=mean[i];b->span[i]=(uint16_t)(high[i]-low[i]);}
 b->status=(uint8_t)((stable&3U)|(rejected<<2));b->variance_q7=(uint8_t)variance_q7;
 b->paths=(uint8_t)paths;b->tick4=(uint8_t)(HAL_GetTick()/4U);
}

static uint8_t pending_pair,pending_valid,pending_active,initialized,lost_sync;
static uint32_t packets;

static pc_capture peak;
static volatile uint32_t peak_epoch;
static uint16_t peak_active_ccr[4],peak_update_cnt,peak_update_cr1;
static uint8_t peak_sealed;

void mic_current_update_epoch(void) {
  if(peak.frozen)return;
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
  /* Capture next-cycle shadows BEFORE calculation and before a possible
   * apex update. If IRQ latency crosses the apex, invalidate the next pair. */
  uint32_t epoch0=peak_epoch,cycles0=DWT->CYCCNT;
  uint32_t u=TIM1->CCR1,v=TIM1->CCR2,w=TIM1->CCR3;
  uint32_t count=TIM1->CNT,direction=TIM1->CR1&TIM_CR1_DIR;
  uint8_t early=!direction && count>=TIM1->CCR4 && count<TIM1->ARR-24U;
  uint32_t isr1=0,isr2=0,jsqr1=0,jsqr2=0;
  if(!peak.frozen){isr1=ADC1->ISR;isr2=ADC2->ISR;jsqr1=ADC1->JSQR;jsqr2=ADC2->JSQR;}
  uint8_t both=(uint8_t)LL_ADC_IsActiveFlag_JEOS(ADC2);
  if(!both)lost_sync=1; /* never combine a prior ADC2 conversion with ADC1 */
  uint16_t a=(uint16_t)(ADC1->JDR1>>4),b=(uint16_t)(ADC2->JDR1>>4);
  LL_ADC_ClearFlag_JEOS(ADC1);LL_ADC_ClearFlag_JEOS(ADC2);
  uint8_t active=(uint8_t)(LL_TIM_IsEnabledAllOutputs(TIM1)!=0);
  uint16_t bus=VBS_GetAvBusVoltage_V(&BusVoltageSensor_M1._Super);
  uint8_t captured_pair=pending_pair,valid0=pending_valid,active0=pending_active;
  uint8_t eligible=(uint8_t)(both && !lost_sync && valid0 && active0 && active && state.zero_ready);
  uint8_t pair=active?cm_choose_pair(u,v,w):(pending_pair==0?2:0);
  pending_valid=early && cm_pair_window(pair,u,v,w,TIM1->CCR4,CM_SETTLE_TICKS);
  pending_active=active;
  queue_pair(pair);
  uint16_t queue_cnt=(uint16_t)TIM1->CNT,queue_dir=(uint16_t)(TIM1->CR1&TIM_CR1_DIR);
  uint32_t queue_cycles=DWT->CYCCNT-cycles0;
  /* Publish the next ADC context BEFORE zero statistics/window calculation. */
  cm_sample(&state,HAL_GetTick(),active,captured_pair,a,b,
            both && !lost_sync && valid0 && active0 && active,
            bus<=20U && both && !lost_sync && early);
  /* Record AFTER publishing the next ADC context. No filtering or control write. */
  if(!peak.frozen && (active || peak.running)) {
    if(queue_cycles>peak.blob.header.reserved)peak.blob.header.reserved=queue_cycles;
    pc_sample sample={0};
    sample.cycles=cycles0;sample.epoch_before=epoch0;
    sample.isr1=isr1;sample.isr2=isr2;sample.jsqr1=jsqr1;sample.jsqr2=jsqr2;
    for(unsigned i=0;i<4;++i){sample.active_ccr[i]=peak_active_ccr[i];sample.offset[i]=state.offset[i];}
    sample.update_cnt=peak_update_cnt;sample.update_cr1=peak_update_cr1;
    sample.epoch_after=peak_epoch;
    sample.preload_ccr[0]=(uint16_t)u;sample.preload_ccr[1]=(uint16_t)v;
    sample.preload_ccr[2]=(uint16_t)w;sample.preload_ccr[3]=(uint16_t)TIM1->CCR4;
    sample.cnt=(uint16_t)count;sample.arr=(uint16_t)TIM1->ARR;sample.cr1=(uint16_t)direction;
    sample.raw[0]=a;sample.raw[1]=b;sample.pair=captured_pair;sample.next_pair=pair;
    sample.cnt_exit=queue_cnt;sample.bus_v=bus;
    sample.reference_deci_hz=(uint16_t)(pACIM_VF_Component_M1->fFlux_Freq_Hz*10.0f);
    uint8_t accepted=(uint8_t)(eligible && a>=16 && b>=16 && a<=4079 && b<=4079);
    sample.flags=(uint16_t)((active?1:0)|(valid0?2:0)|(active0?4:0)|(both?8:0)|
        (lost_sync?16:0)|(early?32:0)|(accepted?64:0)|
        (sample.epoch_before!=sample.epoch_after?128:0)|
        (((isr1|isr2)&ADC_ISR_JQOVF)?256:0)|(queue_dir?512:0));
    int32_t ia=(int32_t)state.offset[cm_path1(captured_pair)]-a;
    int32_t ib=(int32_t)state.offset[cm_path2(captured_pair)]-b,ic=-ia-ib;
    uint32_t mag=(uint32_t)(ia<0?-ia:ia),m=(uint32_t)(ib<0?-ib:ib);
    if(m>mag)mag=m;
    m=(uint32_t)(ic<0?-ic:ic);
    if(m>mag)mag=m;
    pc_push(&peak,&sample,HAL_GetTick(),active,eligible,mag);
  }
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

static const uint16_t zero[4]={2048,2051,2043,2045};
static void conversion(uint32_t ms,int u=0,int v=0,int w=0,bool second=true) {
 tick=ms;int current[3]={u,v,w};
 unsigned p=cm_path1(pending_pair),q=cm_path2(pending_pair);
 unsigned x=pending_pair==2?1:0,y=pending_pair==0?1:2;
 adc1.JDR1=(zero[p]-current[x])<<4;adc2.JDR1=(zero[q]-current[y])<<4;
 adc1.ISR=1;adc2.ISR=second?1:0;
 mic_current_adc_irq();
 check(timer.CCR1==2656 && timer.CCR2==2656 && timer.CCR3==2656 && timer.CCR4==4928);
 check((adc1.JSQR>>8)==(pending_pair==2?7U:1U));
 check((adc2.JSQR>>8)==(pending_pair==0?7U:6U));
}
int regression_main() {
 cm_init(&state);initialized=1;timer={2656,2656,2656,4928,5000,0,5312,0};
 for(unsigned i=0;i<10000;++i)conversion(i/16);
 check(state.zero_ready && !state.zero_bad);
 for(unsigned i=0;i<4;++i)check(state.offset[i]==zero[i]);
 timer.BDTR=32768;bus=323;
 for(unsigned i=0;i<4000;++i)conversion(1000+i/16,100,-40,-60);
 check(cm_window_valid(&state.published));
 check(state.window.last[0]==100 && state.window.last[1]==-40 && state.window.last[2]==-60);
 unsigned rejected=state.window.bad;
 timer.CR1=TIM_CR1_DIR;conversion(1250,100,-40,-60);
 timer.CR1=0;conversion(1251,100,-40,-60);
 check(state.window.bad>rejected);
 conversion(1252,100,-40,-60,false);check(lost_sync);
 unsigned n=state.window.n;
 for(unsigned i=0;i<100;++i)conversion(1253+i/16,100,-40,-60);
 check(state.window.n==n); // a prior ADC2 result can never become a fresh sample
 timer.BDTR=0;conversion(1260);
 check(!state.was_active && (state.published.flags&CM_FROZEN));
 check(packets==0);
 printf("{\"passed\":true,\"checks\":%u,\"power_pwm_registers_unchanged\":true,\"physical_measurements\":false}",checks);
return 0;
}

int main(){
 regression_main();
 cm_init(&state);state.zero_ready=1;
 for(unsigned i=0;i<4;++i)state.offset[i]=zero[i];
 pc_init(&peak);lost_sync=0;pending_pair=0;pending_valid=1;pending_active=1;
 timer={2656,2656,2656,4928,5100,0,5312,32768};
 mic_current_update_epoch();
 for(unsigned i=0;i<20;++i){dwt.CYCCNT+=10625;conversion(2000+i/16,78,-39,-39);}
 check(!peak.frozen && !peak.triggered);
 dwt.CYCCNT+=10625;conversion(2002,1162,-581,-581);
 check(peak.triggered && !peak.frozen);
 for(unsigned i=0;i<6;++i){dwt.CYCCNT+=10625;conversion(2003+i/16,78,-39,-39);}
 check(peak.frozen && peak.blob.header.count==12 && peak.blob.header.flags==PC_PEAK);
 check(peak.blob.header.trigger_sequence+6==peak.blob.header.frozen_sequence);
 auto before=peak.blob;
 for(unsigned i=0;i<10;++i)conversion(2004,1500,-750,-750);
 check(memcmp(&before,&peak.blob,sizeof(before))==0);
 uint8_t packet[UV3_FRAME];
 check(!mic_current_peak_packet(packet,0,2026102506)); // never transmit under PWM
 timer.BDTR=0;
 pc_receiver rx{};
 for(int page=34;page>=0;--page) {
  check(mic_current_peak_packet(packet,(uint8_t)page,2026102506));
  check(!pc_receive(&rx,packet,2026102506,false,1));
  check(!pc_receive(&rx,packet,2026102412,true,1));
  check(pc_receive(&rx,packet,2026102506,true,1));
  check(rx.complete==(page==0));
 }
 check(rx.complete && memcmp(rx.data,&peak.blob,1024)==0);
 check(pc_receive(&rx,packet,2026102506,true,2));
 packet[20]^=1;check(!pc_receive(&rx,packet,2026102506,true,2));
 uv3_seal(packet);check(!pc_receive(&rx,packet,2026102506,true,2));
 FILE *file=fopen("trace.bin","wb");check(file!=nullptr);
 check(fwrite(&peak.blob,1,1024,file)==1024);fclose(file);
 // STOP without reaching threshold is a trace, not a claimed captured peak.
 pc_capture simple{};pc_sample sample{};
 for(unsigned i=0;i<3;++i)pc_push(&simple,&sample,i,1,1,10);
 pc_push(&simple,&sample,4,0,0,0);
 check(simple.frozen && simple.blob.header.flags==PC_NO_PEAK && simple.blob.header.trigger_slot==65535);
 pc_init(&simple);pc_push(&simple,&sample,1,1,1,700);pc_push(&simple,&sample,2,0,0,0);
 check(simple.frozen && simple.blob.header.flags==(PC_PEAK|PC_SHORT));
 printf("{\"passed\":true,\"checks\":%u,\"actual_irq\":true,\"off_only_wire\":true,\"hardware_commands\":0}\n",checks);
}
