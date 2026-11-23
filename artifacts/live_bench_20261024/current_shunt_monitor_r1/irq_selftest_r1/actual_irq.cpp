
#include <cstdint>
#include <cstdio>
#include <cstdlib>
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
static cm_core state;
static uint8_t pending_pair,pending_valid,pending_active,initialized,lost_sync;
static uint32_t packets;

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
int main() {
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
}
