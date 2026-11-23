
#include <cstdint>
#include <cstdio>
#include <cstdlib>
static void on_read();static void on_write();static void deliver();
static uint32_t mask,reads,target,fired,pending,mode;
struct Reg {uint32_t v=0x1000;operator uint32_t(){on_read();return v;}};
struct Timer {Reg BDTR;uint32_t CCER=0x555,ARR=5312,SR=0;};static Timer timer;
#define TIM1 (&timer)
static Timer shadow_timer;
#define TIM8 (&shadow_timer)
#define TIM_BDTR_MOE 0x8000U
#define PIN_CC 0x555U
#define TIM_SR_BIF 128U
#define TIM_SR_B2IF 256U
#define GPIO_PIN_6 64U
struct Gpio {uint32_t IDR=64;};static Gpio ga;
#define GPIOA (&ga)
struct Dwt {uint32_t CYCCNT=170000000;};static Dwt dwt;
#define DWT (&dwt)
static uint32_t state=1,phase=1,protection=0x1000,cached_at=170000000;
static uint32_t SystemCoreClock=170000000,reason,stop,elapsed,start,local_stop;
static bool pins_ok(){return true;}
static bool mic_local_stop_blocked(){return local_stop;}
static uint32_t mic_io_guard(){return 0;}
static uint32_t mic_edges_guard(){return 0;}
static uint32_t __get_PRIMASK(){return mask;}
static void __disable_irq(){mask=1;}
static void __set_PRIMASK(uint32_t v){mask=v;if(!mask&&pending){pending=0;deliver();}}
static void LL_TIM_DisableAllOutputs(Timer*t){t->BDTR.v&=~TIM_BDTR_MOE;on_write();}
static void LL_TIM_DisableIT_UPDATE(Timer*){}
static void counters(unsigned){}

static uint32_t old_guard(void){
 const uint32_t stamp=cached_at,now=DWT->CYCCNT;
 uint32_t bad=0;
 if(SystemCoreClock!=170000000U)bad|=1;
 if(!pins_ok()||(TIM1->BDTR&~TIM_BDTR_MOE)!=protection||TIM1->CCER!=PIN_CC||TIM1->ARR!=5312U)bad|=2;
 if(!(GPIOA->IDR&GPIO_PIN_6)||(TIM1->SR&(TIM_SR_BIF|TIM_SR_B2IF)))bad|=4;
 if(mic_local_stop_blocked())bad|=8;
 if(state==1 && (uint32_t)(now-stamp)>SystemCoreClock/200U)bad|=16;
 if(state==1 && phase>=2 && !(TIM1->BDTR&TIM_BDTR_MOE))bad|=32;
 if((phase<2||state!=1)&&(TIM1->BDTR&TIM_BDTR_MOE))bad|=32;
 return bad|mic_io_guard();
}
static uint32_t guard(void){
 const uint32_t stamp=cached_at,now=DWT->CYCCNT;
 /* The TIM IRQ publishes phase and MOE together. Snapshot both before an
  * IRQ can turn PRE/LOW into ON/HIGH between two foreground reads.
  * Only three loads are protected; hardware BKIN remains asynchronous. */
 const uint32_t mask=__get_PRIMASK();__disable_irq();
 const uint32_t sampled_state=state,sampled_phase=phase,sampled_bdtr=TIM1->BDTR;
 __set_PRIMASK(mask);
 uint32_t bad=0;
 if(SystemCoreClock!=170000000U)bad|=1;
 if(!pins_ok()||(sampled_bdtr&~TIM_BDTR_MOE)!=protection||TIM1->CCER!=PIN_CC||TIM1->ARR!=5312U)bad|=2;
 if(!(GPIOA->IDR&GPIO_PIN_6)||(TIM1->SR&(TIM_SR_BIF|TIM_SR_B2IF)))bad|=4;
 if(mic_local_stop_blocked())bad|=8;
 if(sampled_state==1 && (uint32_t)(now-stamp)>SystemCoreClock/200U)bad|=16;
 if(sampled_state==1 && sampled_phase>=2 && !(sampled_bdtr&TIM_BDTR_MOE))bad|=32;
 if((sampled_phase<2||sampled_state!=1)&&(sampled_bdtr&TIM_BDTR_MOE))bad|=32;
 return bad|mic_edges_guard();
}
static void old_finish(uint32_t why){
 LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableIT_UPDATE(TIM1);
 if(state==1){stop=DWT->CYCCNT;elapsed=stop-start;reason|=why;state=why?3U:2U;counters(6);}
}
static void finish(uint32_t why){
 /* A pending TIM IRQ must never see RUN with an intentionally disabled MOE. */
 const uint32_t mask=__get_PRIMASK();__disable_irq();
 LL_TIM_DisableAllOutputs(TIM1);LL_TIM_DisableAllOutputs(TIM8);LL_TIM_DisableIT_UPDATE(TIM1);
 bool record=false;
 if(state==1){stop=DWT->CYCCNT;elapsed=stop-start;reason|=why;state=why?3U:2U;record=true;}
 __set_PRIMASK(mask);
 if(record)counters(6);
}
static void deliver(){
 if(mode==1){phase=2;timer.BDTR.v|=TIM_BDTR_MOE;}
 else if(mode==2&&state==1){uint32_t b=guard();if(b){reason|=b;state=3;}}
}
static void interrupt(){if(mask)pending=1;else deliver();}
static void on_read(){++reads;if(mode==1&&reads==target&&!fired){fired=1;interrupt();}}
static void on_write(){if(mode==2&&!fired){fired=1;interrupt();}}
static void reset(){state=1;phase=1;timer.BDTR.v=0x1000;timer.SR=0;ga.IDR=64;
 cached_at=dwt.CYCCNT=170000000;mask=reads=target=fired=pending=reason=mode=0;local_stop=0;}
static unsigned checks;
static void test(bool ok){++checks;if(!ok){fprintf(stderr,"race%u\n",checks);exit(1);}}
int main(){
 reset();mode=1;target=2;test(old_guard()==32);test(phase==2&&timer.BDTR.v&0x8000);
 // The same interrupted publication is deferred until the coherent snapshot.
 reset();mode=1;target=1;test(guard()==0);test(phase==2&&timer.BDTR.v&0x8000);test(guard()==0);
 reset();mode=2;phase=2;timer.BDTR.v|=0x8000;old_finish(0);test(state==3&&reason==32);
 reset();mode=2;phase=2;timer.BDTR.v|=0x8000;finish(0);test(state==2&&reason==0);test(!(timer.BDTR.v&0x8000));
 // Real illegal output states and every pre-existing protection still trip.
 reset();phase=2;test(guard()&32);
 reset();timer.BDTR.v|=0x8000;test(guard()&32);
 reset();timer.SR=128;test(guard()&4);
 reset();ga.IDR=0;test(guard()&4);
 reset();local_stop=1;test(guard()&8);
 reset();cached_at-=850001;test(guard()&16);
 reset();timer.BDTR.v^=0x1000;test(guard()&2);
 printf("{\"passed\":true,\"checks\":%u,\"old_enable_race_reproduced\":true,\"old_stop_race_reproduced\":true,\"fixed_enable_and_stop\":true,\"real_fault_negative_controls\":7,\"hardware_calls\":0}\n",checks);
}
