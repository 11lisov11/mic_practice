/* Execute the real diagnostic adapter against fake MMIO, never a device. */
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
struct Timer {uint32_t BDTR=0x1000,CR1=0,DIER=0,ARR=5312,CCR1=2656,CCR2=2656,CCR3=2656,CCR4=4928;};
struct GPIO {uint32_t MODER=0,ODR=0,IDR=0,LCKR=0;};
struct Dwt {uint32_t CYCCNT=0;};
static Timer tim;static GPIO pa,pb;static Dwt dwt;
#define TIM1 (&tim)
#define GPIOA (&pa)
#define GPIOB (&pb)
#define DWT (&dwt)
#define TIM_BDTR_MOE 0x8000U
#define TIM_BDTR_BKE 0x1000U
#define TIM_BDTR_OSSI 0x400U
#define TIM_BDTR_OSSR 0x800U
#define GPIO_PIN_0 1U
#define GPIO_PIN_1 2U
#define GPIO_PIN_7 128U
#define GPIO_PIN_8 256U
#define GPIO_PIN_9 512U
#define GPIO_PIN_10 1024U
#define GPIO_MODE_OUTPUT_PP 1U
#define GPIO_NOPULL 0U
#define GPIO_SPEED_FREQ_LOW 0U
#define GPIO_PIN_RESET 0U
#define __DMB() do{}while(0)
struct GPIO_InitTypeDef {uint32_t Mode,Pull,Speed,Pin;};
static uint32_t SystemCoreClock=170000000U,mic_local_stop_latched;
static uint16_t bus=10;static uint32_t now_ms;
static bool mic_local_stop_blocked(){return mic_local_stop_latched;}
static void LL_TIM_DisableAllOutputs(Timer*t){t->BDTR&=~TIM_BDTR_MOE;}
static void LL_TIM_ClearFlag_UPDATE(Timer*){}
static void LL_TIM_EnableIT_UPDATE(Timer*t){t->DIER|=1;}
static void LL_TIM_DisableIT_UPDATE(Timer*t){t->DIER&=~1U;}
static void HAL_GPIO_WritePin(GPIO*g,uint16_t pins,unsigned){g->ODR&=~pins;g->IDR&=~pins;}
static void HAL_GPIO_Init(GPIO*g,GPIO_InitTypeDef*q){for(unsigned i=0;i<16;i++)if((q->Pin&(1U<<i))&&!(g->LCKR&(1U<<i)))g->MODER=(g->MODER&~(3U<<(2*i)))|(1U<<(2*i));}
static uint32_t HAL_GetTick(){return now_ms;}
static struct {int _Super;} BusVoltageSensor_M1;
static uint16_t VBS_GetAvBusVoltage_V(int*){return bus;}
static uint32_t MC_GetCurrentFaultsMotor1(){return 4;}
static uint32_t MC_GetOccurredFaultsMotor1(){return 1028;}
struct RampExtMngr_Handle_t {uint32_t FrequencyHz=500;};
static RampExtMngr_Handle_t original_ramp;
struct ACIM_VF_Handle_t {float fFlux_Freq_Hz=0,fFlux_Freq_rads=0,fFlux_Angle_rad=0,fVoutMax_PWM_Mod_V=0,fCalcAngleExecFreqHz=16000;RampExtMngr_Handle_t*pRMNGR=&original_ramp;};
static ACIM_VF_Handle_t original;
static ACIM_VF_Handle_t*pACIM_VF_Component_M1=&original;
static unsigned math_calls,fail_math;
static void REMNG_Init(RampExtMngr_Handle_t*){}
static bool ACIM_VF_ExecRamp(ACIM_VF_Handle_t*,int16_t,unsigned){return true;}
static float ACIM_VF_FluxFreqCalc(ACIM_VF_Handle_t*p){p->fFlux_Freq_Hz+=.0033333333f;if(p->fFlux_Freq_Hz>5)p->fFlux_Freq_Hz=5;return p->fFlux_Freq_Hz;}
static void ACIM_VF_CalcAngle(ACIM_VF_Handle_t*p){p->fFlux_Angle_rad+=p->fFlux_Freq_rads/16000;}
static uint16_t ACIM_VF_Controller(ACIM_VF_Handle_t*p){
 ++math_calls;unsigned n=unsigned(p->fFlux_Freq_Hz*10);tim.CCR1=2600+n;tim.CCR2=2700-n;tim.CCR3=2650+n/2;return uint16_t(fail_math);
}
static uint32_t full_bad;
uint32_t mic_full_guard(){return full_bad;}
#include "load_diag.h"
void mic_encoder_load_snapshot(uint32_t*v){std::memset(v,0,17*4);v[0]=now_ms/5;v[11]=7;}
uint32_t mic_current_load_quality(){return 1;}
#include "load_diag.c"
static unsigned checks;
static void test(bool x){++checks;if(!x){std::fprintf(stderr,"platform check%u\n",checks);std::exit(1);}}
static void reset(){
 tim=Timer{};pa=GPIO{};pb=GPIO{};dwt={};bus=10;now_ms=0;mic_local_stop_latched=0;math_calls=0;fail_math=0;
 adc_seen=adc_at=0;updates=adc_calls=adc_accepted=0;tim_max_cycles=adc_max_cycles=tim_max_gap=adc_max_gap=0;
 tim_previous=adc_previous=poll_previous=poll_max_gap=0;cached_at=cached_bad=0;
 mic_load_prepare_pins();pa.LCKR=0x107c2;pb.LCKR=0x10003;
 mic_load_init();dwt.CYCCNT=100;mic_load_adc_enter(100);mic_load_poll();
}
static void request(){mic_load_request=LD_REQUEST;mic_load_poll();}
int main(){
 reset();full_bad=256;test(guard()&256);full_bad=0;

 // Model all relevant ISR preemption positions: an IRQ publishes a newer
 // ADC timestamp after the foreground has obtained its old "now" value.
 // The old subtraction falsely exceeds5ms; the actual corrected guard does not.
 reset();
 for(uint32_t start: {1000U,0xfffffff0U})for(unsigned delta=1;delta<=10000;delta++){
  uint32_t old_now=start;adc_at=start+delta;cached_at=start;
  dwt.CYCCNT=start+delta+1;
  test((uint32_t)(old_now-adc_at)>SystemCoreClock/200U);
  test((guard()&LD_ADC_STALE)==0);
 }
 reset();dwt.CYCCNT=1000000;adc_at=149999;cached_at=1000000;
 test(guard()&LD_ADC_STALE); // Genuine5ms+ ADC age still rejected.
 reset();dwt.CYCCNT=1000000;adc_at=1000000;cached_at=149999;
 test(guard()&LD_ADC_STALE); // Genuine5ms+ foreground age still rejected.

 reset();pa.MODER=(pa.MODER&~mode_mask(pa_mask()))|(2U*output_mode(pa_mask()));
 pb.MODER=(pb.MODER&~mode_mask(pb_mask()))|(2U*output_mode(pb_mask()));
 mic_load_prepare_pins();mic_load_init();request();
 test(!pins_low());test(core.state==LD_DENIED&&(core.reason&LD_CONFIG));
 test(pa.LCKR==0x107c2&&pb.LCKR==0x10003);
 reset();test(core.state==LD_IDLE);test(pins_low());test(!math_calls);test(!mic_load_active());
 request();test(core.state==LD_RUNNING);test(!(tim.BDTR&TIM_BDTR_MOE));
 for(unsigned n=1;n<=80001;n++){
  dwt.CYCCNT=100+n*10625U;now_ms=(dwt.CYCCNT-100)/170000U;
  mic_load_adc_enter(dwt.CYCCNT);mic_load_tim_update();mic_load_adc_exit(dwt.CYCCNT+100,1);
  if(n%8==0)mic_load_poll();
  if(n%32==0)mic_load_medium_update();
  test(!(tim.BDTR&TIM_BDTR_MOE));test(pins_low());
 }
 mic_load_poll();test(core.state==LD_DONE&&core.elapsed>=850000000U&&core.elapsed<850020000U);
 test(math_calls>=79990&&math_calls<=80000);test(adc_calls>=79990);test(adc_accepted>=79990);
 test(ccr_min[0]<ccr_max[0]);test(!(tim.DIER&1));test(tim.CCR1==2656&&tim.CCR2==2656);
 now_ms+=50;mic_load_poll();uint32_t copy[LD_REPORT_WORDS];for(unsigned i=0;i<LD_REPORT_WORDS;i++)copy[i]=mic_load_report[i];
 test(copy[4]==copy[69]&&!(copy[4]&1));test(ld_crc(copy+5,64)==copy[70]);
 test(copy[36]==4&&copy[37]==1028);test(copy[26]==10&&copy[27]==327);test(copy[38]==1);
 unsigned calls=math_calls;request();test(!mic_load_active()&&math_calls==calls);
 reset();bus=20;request();test(core.state==LD_DENIED&&(core.reason&LD_BUS));test(!math_calls);
 reset();request();tim.BDTR|=TIM_BDTR_MOE;mic_load_tim_update();test(core.state==LD_ABORTED&&(core.reason&LD_OUTPUT));test(!(tim.BDTR&TIM_BDTR_MOE));
 reset();request();tim.BDTR^=TIM_BDTR_BKE;mic_load_tim_update();test(core.state==LD_ABORTED&&(core.reason&LD_CONFIG));
 reset();request();dwt.CYCCNT+=1000000U;mic_load_tim_update();test(core.state==LD_ABORTED&&(core.reason&LD_ADC_STALE));
 reset();mic_local_stop_latched=1;request();test(core.state==LD_DENIED&&(core.reason&LD_LOCAL_STOP));
 reset();mic_load_request=0xdeadbeef;mic_load_poll();test(core.state==LD_DENIED&&(core.reason&LD_COMMAND));
 reset();request();fail_math=1;mic_load_tim_update();test(core.state==LD_ABORTED&&(core.reason&LD_MATH));
 reset();request();mic_load_request=LD_CANCEL;mic_load_poll();test(core.state==LD_ABORTED&&(core.reason&LD_COMMAND));
 reset();request();pa.MODER=0;mic_load_poll();test(core.state==LD_ABORTED&&(core.reason&LD_CONFIG));
 std::printf("{\"passed\":true,\"checks\":%u,\"hardware_calls\":0,\"scope\":\"adapter with fake MMIO; PWM math is stubbed\"}\n",checks);
}
