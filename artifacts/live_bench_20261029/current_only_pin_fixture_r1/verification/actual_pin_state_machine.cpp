
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include "load_core.h"
struct Timer {uint32_t BDTR,CCER,ARR,CCR1,CCR2,CCR3,EGR,SR,CR1,DIER,RCR,PSC,AF1,SMCR;};
struct Gpio {uint32_t MODER,AFR[2],IDR;};
struct Counter {uint32_t CYCCNT;};struct Clocks {uint32_t AHB2ENR;};struct Tick {uint32_t LOAD;};
static Timer timer;static Gpio ga,gb;static Counter dwt;static Clocks rcc;static Tick systick;
#define TIM1 (&timer)
#define GPIOA (&ga)
#define GPIOB (&gb)
#define DWT (&dwt)
#define RCC (&rcc)
#define SysTick (&systick)
#define GPIO_PIN_6 64U
#define TIM_BDTR_MOE 32768U
#define TIM_BDTR_BKE 4096U
#define TIM_BDTR_AOE 16384U
#define TIM_SR_BIF 128U
#define TIM_SR_B2IF 256U
#define TIM_CR1_CEN 1U
#define TIM_EGR_UG 1U
static uint32_t SystemCoreClock=170000000U;
static volatile uint32_t mic_local_stop_latched;
static bool mic_local_stop_blocked(){return mic_local_stop_latched!=0;}
static uint32_t HAL_GetTick(){return dwt.CYCCNT/170000U;}
static void __DMB(){}
static void LL_TIM_DisableAllOutputs(Timer*t){t->BDTR&=~TIM_BDTR_MOE;}
static void LL_TIM_DisableIT_UPDATE(Timer*t){t->DIER&=~1U;}
static void LL_TIM_EnableIT_UPDATE(Timer*t){t->DIER|=1U;}
static void LL_TIM_DisableIT_BRK(Timer*t){t->DIER&=~128U;}
static void LL_TIM_EnableIT_BRK(Timer*t){t->DIER|=128U;}
static void LL_TIM_ClearFlag_UPDATE(Timer*t){t->SR&=~1U;}
static void check(bool ok){if(!ok)std::abort();}
/* ISOLATED LOGIC FIXTURE ONLY. The34-pin inverter cable must be removed.
 * No AS5600 code or motor-control scheduler/UART/ADC is started.
 * Original TIM1 pins, deadtime and hardware BKIN. One5s request per boot.
 */







#define PIN_BUILD 2026102990U
#define PIN_REQUEST 0x50494e35U
#define PIN_CANCEL 0x50494e00U
#define PIN_CC 0x555U
volatile uint32_t mic_pin_request;
volatile uint32_t mic_pin_report[64];
static volatile uint32_t state,reason,attempted,start,stop,elapsed,phase,updates;
static volatile uint32_t cached_at,max_cost,max_gap,break_sr;
static uint32_t protection,previous_irq,previous_poll,max_poll_gap,seq,publish_ms;
static uint32_t boundaries[8];
static uint32_t pins_ok(void){
 const uint32_t am=(3U<<14)|(3U<<16)|(3U<<18)|(3U<<20);
 return (GPIOA->MODER&am)==((2U<<14)|(2U<<16)|(2U<<18)|(2U<<20)) &&
   (GPIOB->MODER&15U)==10U && (GPIOA->AFR[0]>>28)==6U &&
   (GPIOA->AFR[1]&0xfffU)==0x666U && (GPIOB->AFR[0]&255U)==0x66U;
}
static uint32_t guard(void){
 const uint32_t stamp=cached_at,now=DWT->CYCCNT;
 uint32_t bad=0;
 if(SystemCoreClock!=170000000U)bad|=1;
 if(!pins_ok()||(TIM1->BDTR&~TIM_BDTR_MOE)!=protection||TIM1->CCER!=PIN_CC||TIM1->ARR!=5312U)bad|=2;
 if(!(GPIOA->IDR&GPIO_PIN_6)||(TIM1->SR&(TIM_SR_BIF|TIM_SR_B2IF)))bad|=4;
 if(mic_local_stop_blocked())bad|=8;
 if(state==1 && (uint32_t)(now-stamp)>SystemCoreClock/200U)bad|=16;
 if(state==1 && phase>=2 && !(TIM1->BDTR&TIM_BDTR_MOE))bad|=32;
 if((phase<2||state!=1)&&(TIM1->BDTR&TIM_BDTR_MOE))bad|=32;
 return bad;
}
static void counters(unsigned offset) {(void)offset;}
static void finish(uint32_t why){
 LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableIT_UPDATE(TIM1);
 if(state==1){stop=DWT->CYCCNT;elapsed=stop-start;reason|=why;state=why?3U:2U;counters(6);}
}
static bool tick(void){
 if(state!=1)return false;
 const uint32_t now=DWT->CYCCNT,bad=guard();elapsed=now-start;
 if(bad){finish(bad);return false;}
 if(elapsed>=SystemCoreClock*5U){finish(0);return false;}
 return true;
}
void mic_pin_init(void){
 LL_TIM_DisableAllOutputs(TIM1);TIM1->DIER=0;TIM1->SMCR=0;
 TIM1->CCER=PIN_CC;
 TIM1->CCR1=TIM1->ARR/4;TIM1->CCR2=TIM1->ARR/2;TIM1->CCR3=3*TIM1->ARR/4;
 TIM1->EGR=TIM_EGR_UG;TIM1->SR=0;
 protection=TIM1->BDTR&~TIM_BDTR_MOE;
 /* Never clear a subsequent Break, never enable automatic rearm. */
 if(!(protection&TIM_BDTR_BKE)||(protection&TIM_BDTR_AOE))reason|=2;
 TIM1->CR1|=TIM_CR1_CEN;
 LL_TIM_EnableIT_BRK(TIM1);cached_at=DWT->CYCCNT;publish_ms=HAL_GetTick()-50U;
}
void mic_pin_break(void){
 break_sr=TIM1->SR;LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableIT_BRK(TIM1);
 if(state==1)finish(4);else reason|=4;
}
void mic_pin_irq(void){
 LL_TIM_ClearFlag_UPDATE(TIM1);
 if(!tick())return;
 uint32_t now=DWT->CYCCNT;
 if(previous_irq){uint32_t d=now-previous_irq;if(d>max_gap)max_gap=d;}previous_irq=now;
 ++updates;uint32_t cost=DWT->CYCCNT-now;if(cost>max_cost)max_cost=cost;
}
static void publish(void){
 uint32_t v[64]={0};v[0]=0x314e4950U;v[1]=1;v[2]=PIN_BUILD;v[3]=64;
 v[5]=state;v[6]=reason;v[7]=attempted;v[8]=start;v[9]=stop;v[10]=elapsed;v[11]=SystemCoreClock;
 v[12]=updates;v[13]=max_cost;v[14]=max_gap;v[15]=max_poll_gap;v[16]=phase;
 v[17]=TIM1->BDTR;v[18]=TIM1->CR1;v[19]=TIM1->ARR;
 v[20]=TIM1->CCR1;v[21]=TIM1->CCR2;v[22]=TIM1->CCR3;v[23]=GPIOA->IDR;
 v[24]=mic_local_stop_latched;v[25]=TIM1->RCR;v[26]=RCC->AHB2ENR;v[27]=TIM1->PSC;
 /* No encoder in this fixture. */for(unsigned i=0;i<8;i++)v[45+i]=boundaries[i];
 v[53]=TIM1->CCER;v[54]=TIM1->AF1;v[55]=GPIOA->MODER;v[56]=GPIOB->MODER;
 v[57]=break_sr;v[58]=TIM1->SMCR;v[59]=TIM1->DIER;v[60]=SysTick->LOAD;
 seq+=2;v[4]=v[61]=seq;v[62]=ld_crc(v+5,56);v[63]=0x50494e45U;
 mic_pin_report[4]=seq|1U;__DMB();
 for(unsigned i=0;i<64;i++)if(i!=4)mic_pin_report[i]=v[i];
 __DMB();mic_pin_report[4]=seq;
}
void mic_pin_poll(void){
 const uint32_t now=DWT->CYCCNT;
 if(previous_poll){uint32_t gap=now-previous_poll;if(gap>max_poll_gap)max_poll_gap=gap;}
 previous_poll=now;cached_at=now;
 if(mic_pin_request){
  uint32_t r=mic_pin_request;mic_pin_request=0;
  if(r==PIN_CANCEL){if(state==1)finish(128);}
  else if(!attempted){
   attempted=1;reason|=guard();
   if(r!=PIN_REQUEST)reason|=128;
   if(reason){state=4;}
   else {
    phase=2;start=DWT->CYCCNT;__DMB();state=1;
    LL_TIM_ClearFlag_UPDATE(TIM1);LL_TIM_EnableIT_UPDATE(TIM1);
    TIM1->BDTR|=TIM_BDTR_MOE;
    if(guard())finish(guard());
   }
  }
 }
 if(state==1)(void)tick();
 uint32_t ms=HAL_GetTick();if((uint32_t)(ms-publish_ms)>=50){publish_ms=ms;publish();}
}

int main(int argc,char**argv){
 unsigned c=argc>1?unsigned(std::atoi(argv[1])):0;
 timer.BDTR=TIM_BDTR_BKE|0x9050;timer.ARR=5312;
 ga.MODER=(2U<<14)|(2U<<16)|(2U<<18)|(2U<<20);ga.AFR[0]=6U<<28;ga.AFR[1]=0x666;
 gb.MODER=10;gb.AFR[0]=0x66;ga.IDR=GPIO_PIN_6;systick.LOAD=169999;
 mic_pin_init();check(!(timer.BDTR&TIM_BDTR_MOE));
 if(c==4)SystemCoreClock=160000000;
 mic_pin_request=PIN_REQUEST;mic_pin_poll();
 if(c==4){check(state==4 && !(timer.BDTR&TIM_BDTR_MOE));return 0;}
 check(state==1 && (timer.BDTR&TIM_BDTR_MOE));
 check(timer.CCR1==1328 && timer.CCR2==2656 && timer.CCR3==3984);
 if(c==1){mic_pin_request=PIN_CANCEL;mic_pin_poll();check(state==3 && reason==128);}
 if(c==2){ga.IDR=0;mic_pin_irq();check(state==3 && (reason&4));}
 if(c==3){dwt.CYCCNT+=850001;mic_pin_irq();check(state==3 && (reason&16));}
 if(c==5){mic_local_stop_latched=1;mic_pin_irq();check(state==3 && (reason&8));}
 if(c==0){
  for(unsigned i=0;i<80010 && state==1;i++){dwt.CYCCNT+=10624;mic_pin_poll();mic_pin_irq();}
  check(state==2 && reason==0 && elapsed>=850000000 && elapsed<850011000);
  mic_pin_request=PIN_REQUEST;mic_pin_poll();check(state==2 && attempted==1);
 }
 check(!(timer.BDTR&TIM_BDTR_MOE));return 0;
}
