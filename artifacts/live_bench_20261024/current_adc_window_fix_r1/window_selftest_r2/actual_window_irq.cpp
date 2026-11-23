
#include <cstdint>
#include <cstdio>
#include <cstdlib>
static void mic_zero_record(unsigned attempt,unsigned stable,unsigned rejected,
 const uint16_t *mean,const uint16_t *low,const uint16_t *high,unsigned variance_q7,unsigned paths);
#define CM_ZERO_REPORT(s,mean,var,paths) mic_zero_record((s)->zero_attempts,(s)->zero_stable,(s)->zero_last_bad,mean,(s)->zero_low,(s)->zero_high,var,paths)
#include "current_core.h"
#include "current_adc_window_plan.h"
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
enum {CM_SETTLE_TICKS=771,CM_BEFORE_TOP=384,CM_ACQUIRE_TICKS=112};
static uint32_t tick;
static uint16_t bus;
static struct {int _Super;} BusVoltageSensor_M1;
static uint32_t HAL_GetTick(){return tick;}
static void(*bus_hook)();
static uint16_t VBS_GetAvBusVoltage_V(int*){if(bus_hook)bus_hook();return bus;}
static uint32_t LL_TIM_IsEnabledAllOutputs(Timer *t){return t->BDTR&32768;}
static unsigned LL_ADC_IsActiveFlag_JEOS(Adc *a){return a->ISR&1;}
static void LL_ADC_ClearFlag_JEOS(Adc *a){a->ISR&=~1U;}
static unsigned checks;
static void check_at(bool okay,unsigned line){++checks;if(!okay){fprintf(stderr,"IRQ check %u failed at line%u\n",checks,line);exit(1);}}

#define check(value) check_at((value),__LINE__)

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
struct Frame{unsigned ccr[4],next[4],raw[2],cnt,cycles;};static Frame replay[]={
{{601,2684,4673,4928},{622,2655,4688,4928},{2168,1969},5230,4080261577U},
{{622,2655,4688,4928},{637,2626,4709,4928},{2147,1951},5229,4080272200U},
{{637,2626,4709,4928},{660,2583,4723,4928},{2112,1924},5226,4080282821U},
{{660,2583,4723,4928},{683,2554,4743,4928},{2161,1971},5230,4080293449U},
{{683,2554,4743,4928},{699,2511,4757,4928},{2419,2209},5229,4080304072U},
{{699,2511,4757,4928},{723,2482,4776,4928},{1719,1665},5226,4080314693U},
{{723,2482,4776,4928},{740,2439,4788,4928},{2153,1965},5229,4080325320U},
{{740,2439,4788,4928},{765,2410,4806,4928},{2242,1982},5231,4080335946U},
{{765,2410,4806,4928},{783,2367,4823,4928},{2155,1959},5226,4080346565U},
{{783,2367,4823,4928},{809,2338,4834,4928},{2165,1963},5228,4080357191U},
{{809,2338,4834,4928},{827,2296,4850,4928},{2158,1954},5229,4080367816U},
{{827,2296,4850,4928},{855,2267,4861,4928},{2166,1962},5233,4080378444U},
};

static void reset_test(){
 cm_init(&state);state.zero_ready=1;pc_init(&peak);peak_sealed=0;
 for(unsigned i=0;i<4;++i)state.offset[i]=2067;
 lost_sync=0;pending_pair=0;pending_valid=0;pending_active=0;peak_epoch=0;
 initialized=1;bus=320;timer={2656,2656,2656,4928,0,0,5312,32768};
 bus_hook=nullptr;
}
// CCR fields model readable preload registers. 'active' only changes on UEV.
// Writing CH4 while counting MUST leave the current cycle's active CCR alone.
static uint16_t active_ccr[4];
static void update(unsigned u,unsigned v,unsigned w){
 active_ccr[0]=(uint16_t)timer.CCR1;active_ccr[1]=(uint16_t)timer.CCR2;
 active_ccr[2]=(uint16_t)timer.CCR3;active_ccr[3]=(uint16_t)timer.CCR4;
 timer.CNT=110;timer.CR1=0;mic_current_update_epoch();
 timer.CCR1=u;timer.CCR2=v;timer.CCR3=w;
}
static void conversion(unsigned n,int ia=78,int ib=-39,bool second=true){
 tick=1000+n/16;timer.CNT=active_ccr[3]+302;timer.CR1=0;dwt.CYCCNT+=10624;
 unsigned x=cm_path1(pending_pair),y=cm_path2(pending_pair);
 adc1.JDR1=(state.offset[x]-ia)<<4;adc2.JDR1=(state.offset[y]-ib)<<4;
 adc1.ISR=1;adc2.ISR=second?1:0;
 unsigned power[3]={timer.CCR1,timer.CCR2,timer.CCR3};
 unsigned old_active=active_ccr[3];
 mic_current_adc_irq();
 check(timer.CCR1==power[0] && timer.CCR2==power[1] && timer.CCR3==power[2]);
 check(active_ccr[3]==old_active); // no immediate CH4/trigger change
 check(timer.CCR4<=4928 && timer.CCR4>0);
 check((adc1.JSQR>>8)==(pending_pair==2?7U:1U));
 check((adc2.JSQR>>8)==(pending_pair==0?7U:6U));
}
int main(){
 // Independent brute-force interval oracle on a dense small-integer domain.
 for(unsigned u=0;u<=30;u+=2)for(unsigned v=0;v<=30;v+=2)
 for(unsigned w=0;w<=30;w+=2){
  auto plan=mic_plan_current_window(u,v,w,30,5,2);
  unsigned c[3]={u,v,w};unsigned excluded=u>=v&&u>=w?0:v>=w?1:2;
  bool found=false;
  for(unsigned t=1;t<=30;++t){
   bool okay=t>5;
   for(unsigned j=0;j<3;++j){
    if(j!=excluded && (c[j]+5>=t))okay=false;
    if(c[j]+5>=t && c[j]<=t+2)okay=false;
   }
   found|=okay;
   check(mic_current_window_safe(plan.pair,u,v,w,t,5,2)==okay);
  }
  check(bool(plan.valid)==found);
  if(found)check(mic_current_window_safe(plan.pair,u,v,w,plan.trigger,5,2));
 }
 check(!mic_current_window_safe(3,0,0,0,100,5,2));
 check(!mic_current_window_safe(0,0,0,0,0xffffffffU,5,2));
 check(!mic_plan_current_window(5000,5000,5000,4928,771,112).valid);
 // The physical trigger frame must fail the NEW geometry check, while a
 // counterfactual different trigger is safe. It is not a remeasured ADC value.
 FILE *csv=fopen("window_replay.csv","w");check(csv!=nullptr);
 fprintf(csv,"frame,old_trigger,new_trigger,new_pair,u_compare,v_compare,w_compare,old_safe,new_safe,raw1,raw2\n");
 unsigned ordinal=0;
 for(auto &x:replay){
  check(cm_pair_window(0,x.ccr[0],x.ccr[1],x.ccr[2],x.ccr[3],771));
  check(!mic_current_window_safe(0,x.ccr[0],x.ccr[1],x.ccr[2],x.ccr[3],771,112));
  auto plan=mic_plan_current_window(x.ccr[0],x.ccr[1],x.ccr[2],4928,771,112);
  check(plan.valid && plan.trigger!=4928);
  check(mic_current_window_safe(plan.pair,x.ccr[0],x.ccr[1],x.ccr[2],plan.trigger,771,112));
  fprintf(csv,"%u,%u,%u,%u,%u,%u,%u,0,1,%u,%u\n",ordinal++,x.ccr[3],plan.trigger,plan.pair,x.ccr[0],x.ccr[1],x.ccr[2],x.raw[0],x.raw[1]);
 }
 fclose(csv);
 // Replay the ACTUAL raw pairs/CCRs, not a fabricated shifted waveform.
 reset_test();
 for(unsigned n=0;n<12;++n){auto &x=replay[n];
  for(unsigned j=0;j<4;++j)peak_active_ccr[j]=x.ccr[j];
  peak_epoch=n+1;pending_pair=0;pending_valid=1;pending_active=1;
  timer.CCR1=x.next[0];timer.CCR2=x.next[1];timer.CCR3=x.next[2];timer.CCR4=x.ccr[3];
  timer.CNT=x.cnt;timer.CR1=0;tick=2000;dwt.CYCCNT=x.cycles;
  adc1.ISR=1;adc2.ISR=1;adc1.JDR1=x.raw[0]<<4;adc2.JDR1=x.raw[1]<<4;
  mic_current_adc_irq();
 }
 check(state.window.n==0 && state.window.bad==12);
 check((state.window.flags&CM_TIMING)!=0);
 check(peak.frozen && peak.blob.header.flags==PC_PEAK && peak.blob.header.count==12);
 auto &trigger=peak.blob.samples[peak.blob.header.trigger_slot];
 check(trigger.raw[0]==1719 && trigger.raw[1]==1665);
 check((trigger.flags&1024)!=0 && (trigger.flags&64)==0);
 uint8_t packet[UV3_FRAME];timer.BDTR=0;
 pc_receiver rx{};
 for(int page=34;page>=0;--page){
  check(mic_current_peak_packet(packet,page,CT_PEER_BUILD));
  check(pc_receive(&rx,packet,CT_PEER_BUILD,true,1));
 }
 check(rx.complete && memcmp(rx.data,&peak.blob,1024)==0);
 FILE *f=fopen("replayed_trace.bin","wb");check(f!=nullptr);
 check(fwrite(&peak.blob,1,1024,f)==1024);fclose(f);
 // Cycle pipeline: current sample uses the previously committed tuple;
 // plan for NEXT shadows is not treated as though already active.
 reset_test();
 for(unsigned n=0;n<8000;++n){
  unsigned w=4600+(n%60)*5;
  update(700,2500,w);conversion(n);
  if(n>2)check(mic_current_window_safe(pending_pair,700,2500,w,timer.CCR4,771,112));
 }
 check(cm_window_valid(&state.published) && state.published.bad==0);
 check(state.window.last[0]==78 && state.window.last[1]==-39 && state.window.last[2]==-39);
 // Rotate all three shadows, including changes of reconstructed phase.
 // Encode known currents through the PREVIOUS queued mux tuple.
 reset_test();
 for(unsigned n=0;n<10000;++n){
  unsigned u=500+n%4000,v=500+(n+1333)%4000,w=500+(n+2666)%4000;
  update(u,v,w);
  unsigned captured=pending_pair,valid=pending_valid,active=pending_active;
  bool expected=valid && active && mic_current_window_safe(captured,
      active_ccr[0],active_ccr[1],active_ccr[2],active_ccr[3],771,112);
  int currents[3]={100,-40,-60};
  conversion(n,currents[captured==2?1:0],currents[captured==0?1:2]);
  auto &sample=peak.blob.samples[(peak.write+11)%12];
  check(sample.pair==captured && bool(sample.flags&64)==expected);
  for(unsigned j=0;j<4;++j)check(sample.active_ccr[j]==active_ccr[j]);
  const auto &latest=state.published.end_ms==tick?state.published:state.window;
  if(expected)for(unsigned j=0;j<3;++j)check(latest.last[j]==currents[j]);
 }
 // Genuine large counts in a safe window are preserved, never amplitude-clipped.
 reset_test();
 for(unsigned n=0;n<20;++n){update(2656,2656,2656);conversion(n);}
 update(2656,2656,2656);conversion(20,1162,-581);
 check(peak.triggered && state.window.peak[1]==1162);
 for(unsigned n=21;n<27;++n){update(2656,2656,2656);conversion(n);}
 check(peak.frozen && peak.blob.header.flags==PC_PEAK);
 // Even frozen diagnostic storage must not stop epoch tracking for monitoring.
 unsigned ep=peak_epoch;update(2656,2656,2656);check(peak_epoch==ep+1);
 unsigned old_n=state.window.n;conversion(27);check(state.window.n==old_n+1);
 // Wrong context, missing ADC2, JQ overflow, and no safe window fail closed.
 reset_test();update(2656,2656,2656);conversion(0);
 update(2656,2656,2656);++peak_active_ccr[3];old_n=state.window.n;conversion(1);
 check(state.window.n==old_n && state.window.bad>0);
 reset_test();update(2656,2656,2656);conversion(0);
 update(2656,2656,2656);conversion(1,78,-39,false);check(lost_sync);
 old_n=state.window.n;update(2656,2656,2656);conversion(2);check(state.window.n==old_n);
 reset_test();update(5000,5000,5000);conversion(0);check(!pending_valid);
 update(5000,5000,5000);old_n=state.window.n;conversion(1);check(state.window.n==old_n);
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 bus_hook=[](){++peak_epoch;};old_n=state.window.n;conversion(1);
 check(!pending_valid && state.window.n==old_n);bus_hook=nullptr;
 reset_test();update(2656,2656,2656);conversion(0);update(2656,2656,2656);
 timer.CNT=5230;adc1.ISR=1|ADC_ISR_JQOVF;adc2.ISR=1;mic_current_adc_irq();check(lost_sync);
 // Real OFF IRQ path still alternates four ADC paths and completes the same
 // three-block zero sequence at low bus; no power PWM or trace trigger.
 reset_test();state.zero_ready=0;timer.BDTR=0;bus=10;
 for(unsigned n=0;n<10000;++n){update(2656,2656,2656);conversion(n,0,0);}
 check(state.zero_ready && !state.zero_bad && state.zero_stable==3 && state.zero_attempts==3);
 for(unsigned j=0;j<4;++j)check(state.offset[j]==2067 && state.count[j]==256);
 check(!peak.running && !peak.frozen && peak.count==0);
 check(packets==0);
 printf("{\"passed\":true,\"checks\":%u,\"actual_irq\":true,\"real_trace_frames_replayed\":12,\"new_waveform_synthetic\":true,\"preload_epoch_pipeline_model\":true,\"hardware_commands\":0}\n",checks);
}
