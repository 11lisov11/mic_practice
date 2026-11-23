#include <cassert>
#include <cstdio>
#include <cstring>
#include "repeat_state.h"
#include "break_wire.h"
#include "bkin_wave_wire.h"
#include "repeat_wave_wire.h"
#include "boot_wire.h"
#include "bkin_wave_capture.h"
#include "pulse_record.h"
// C's enum constant is an int; use the same unsigned value in the C++ fixture.
#define BP_PRE 2048U
#define __DMB() do{}while(0)
#define GPIO_PIN_4 16U
#define GPIO_PIN_6 64U
#define TIM_SR_BIF 128U
#define TIM_SR_B2IF 256U
#define TIM_CR2_MMS 112U
#define TIM_EGR_UG 1U
#define GPIO_MODE_INPUT 0U
#define GPIO_NOPULL 0U
#define HAL_OK 0
#define HAL_ERROR 1
#define HAL_DMA_STATE_READY 0U
#define HAL_DMA_STATE_BUSY 1U
#define DMA2_Channel1_IRQn 1
#define DMA_CCR_HTIE 4U
#define DMA_CCR_TCIE 2U
#define DMA_CCR_TEIE 8U
#define TIM_DIER_UDE 256U
#define TIM_CR1_CEN 1U
#define RCC_HCLK_DIV1 1U
#define MIC_BKIN_DMA_ACK(mask) do{(void)(mask);}while(0)
struct Timer{uint32_t SR=0,DIER=0,BDTR=0x1000,CNT=0,ARR=5312,CCR1=2656,CCR2=2656,CCR3=2656,CR1=0,CR2=0,PSC=0,EGR=0;};
struct GPIO{uint32_t IDR=0x50,MODER=0,PUPDR=0;};
Timer tim1,tim2;Timer*TIM1=&tim1;Timer*TIM2=&tim2;GPIO gpio;GPIO*GPIOA=&gpio;
struct DmaChannel{uint32_t CNDTR=8192,CCR=0;}channel;DmaChannel*DMA2_Channel1=&channel;
struct DmaHandle{uint32_t State=HAL_DMA_STATE_BUSY;}hdma_mic_bkin;
struct RCC_ClkInitTypeDef{uint32_t APB1CLKDivider=2;};
struct GPIO_InitTypeDef{uint32_t Pin=0,Mode=0,Pull=0;};
struct {bool command_enabled=false;}uno_link;
bool fail_start=false,fail_abort=false,race_start=false,fail_gpio=false;unsigned aborts=0;
uint32_t fake_tick=0;
uint32_t HAL_GetTick(){return fake_tick;}
void HAL_NVIC_DisableIRQ(int){}void HAL_NVIC_ClearPendingIRQ(int){}
void HAL_NVIC_SetPriority(int,int,int){}void HAL_NVIC_EnableIRQ(int){}
bool LL_TIM_IsEnabledAllOutputs(Timer*t){return t->BDTR&0x8000;}
void HAL_RCC_GetClockConfig(RCC_ClkInitTypeDef*,uint32_t*){}
uint32_t HAL_RCC_GetPCLK1Freq(){return 85000000;}
void HAL_GPIO_Init(GPIO*g,GPIO_InitTypeDef*){g->MODER=fail_gpio?3U<<8:0;g->PUPDR=0;}
int HAL_DMA_Abort(DmaHandle*h){++aborts;if(fail_abort)return HAL_ERROR;h->State=HAL_DMA_STATE_READY;return HAL_OK;}
void inject_start_irq();
int HAL_DMA_Start(DmaHandle*h,uint32_t,uint32_t,uint32_t n){
 if(fail_start||h->State!=HAL_DMA_STATE_READY)return HAL_ERROR;
 h->State=HAL_DMA_STATE_BUSY;channel.CNDTR=n;if(race_start)inject_start_irq();return HAL_OK;
}
#include "first_break_snapshot.h"
volatile mic_break_snapshot_t mic_first_break={},mic_first_start_break={},mic_after_clear_break={};
volatile uint32_t mic_break_start_window=0,mic_break_irq_count=0,mic_break_context_index=0,mic_break_context_valid=0;
volatile mic_break_context_t mic_break_context[2]={};
volatile rp_state mic_repeat_state={};
uint8_t mic_bkin_record[320]={},mic_repeat_wave[320]={};
uint32_t mic_bkin_record_crc=0,mic_repeat_wave_crc=0;
volatile uint32_t mic_bkin_record_ready=0,mic_repeat_wave_ready=0;
bool mic_repeat_active=false;
volatile uint32_t mic_bkin_capture_state=MIC_BKIN_RUNNING,mic_bkin_event_tick_ms=0,mic_bkin_dma_flags=0,mic_bkin_remaining=0;
uint32_t mic_bkin_triggered=0,mic_bkin_completed=0,mic_bkin_has_history=0,mic_bkin_cursor=0;
uint32_t mic_bkin_stream_error=0;uint8_t mic_bkin_ring[8192]={};
bp_capture mic_bkin_pulse={};bool mic_bkin_dma_initialized=true;
void mic_bkin_capture_init(){}
void mic_bkin_freeze(){mic_bkin_capture_state=MIC_BKIN_CAPTURED;}
// ACTUAL_FUNCTIONS
void inject_start_irq(){tim1.SR=128;mic_break_capture_first(fake_tick);}
static void reset(){
 memset((void*)&mic_repeat_state,0,sizeof(mic_repeat_state));memset((void*)&mic_first_break,0,sizeof(mic_first_break));
 memset((void*)&mic_after_clear_break,0,sizeof(mic_after_clear_break));
 mic_repeat_active=false;mic_repeat_wave_ready=mic_bkin_record_ready=0;mic_break_irq_count=0;mic_bkin_triggered=0;
 mic_bkin_capture_state=MIC_BKIN_RUNNING;bp_init(&mic_bkin_pulse);tim1={};tim2={};gpio={};
 fail_start=fail_abort=race_start=fail_gpio=false;hdma_mic_bkin.State=HAL_DMA_STATE_BUSY;aborts=0;
 mic_bkin_has_history=1;mic_bkin_completed=0;channel.CNDTR=6144;fake_tick=1000;
}
static void wave(unsigned low){
 bp_init(&mic_bkin_pulse);mic_bkin_pulse.trigger=2048;
 bp_feed_span(&mic_bkin_pulse,3,2040);bp_feed_span(&mic_bkin_pulse,0,low);
 bp_feed_span(&mic_bkin_pulse,3,400);mic_bkin_capture_state=MIC_BKIN_CAPTURED;
}
static void first(){reset();tim1.SR=128;mic_break_capture_first(1000);wave(4);mic_bkin_prepare_record();assert(mic_bkin_record_ready&&bp_record_valid(mic_bkin_record));}
static void packet(uint8_t*p,const uint8_t*record,unsigned page){
 memset(p,0,43);p[0]=0x55;p[1]=0xaa;p[2]=RPW_VERSION;p[3]=page;p[4]=RPW_PAGES;
 bw_put32(p+6,RP_NATIVE_BUILD);bw_put32(p+10,uv3_crc32c(record,320));
 unsigned off=page*24,n=320-off;if(n>24)n=24;memcpy(p+14,record+off,n);uv3_seal(p);
}
int main(){
 unsigned checks=0;first();uint8_t first_wave[320],first_snap[92];memcpy(first_wave,mic_bkin_record,320);memcpy(first_snap,(const void*)&mic_first_break,92);
 fake_tick=2000;mic_repeat_capture_arm(2000);assert(mic_repeat_state.state==RP_ARMED&&aborts==1&&mic_bkin_capture_state==MIC_BKIN_RUNNING);++checks;
 assert(memcmp(first_wave,mic_bkin_record,320)==0&&memcmp(first_snap,(const void*)&mic_first_break,92)==0);++checks;
 fake_tick=2020;channel.CNDTR=6144;tim1.SR=128;mic_break_capture_first(2020);wave(20);mic_bkin_prepare_record();
 assert(mic_repeat_wave_ready&&mic_repeat_state.state==RP_CAPTURED&&mic_repeat_state.event_irq==2&&mic_after_clear_break.tick_ms==2020);++checks;
 assert(bp_record_valid(mic_repeat_wave)&&memcmp(first_wave,mic_bkin_record,320)==0&&memcmp(first_snap,(const void*)&mic_first_break,92)==0);++checks;
 uint8_t repeat_wave[320],repeat_snap[92];memcpy(repeat_wave,mic_repeat_wave,320);memcpy(repeat_snap,(const void*)&mic_after_clear_break,92);
 mic_repeat_capture_arm(3000);mic_break_capture_first(3020);mic_bkin_prepare_record();
 assert(memcmp(repeat_wave,mic_repeat_wave,320)==0&&memcmp(repeat_snap,(const void*)&mic_after_clear_break,92)==0&&mic_repeat_state.clear_tick==2000);++checks;
 rpw_receiver rx={};uint8_t p[43];
 for(unsigned i=0;i<RPW_PAGES;++i){packet(p,repeat_wave,i);assert(rpw_receive(&rx,p,RP_NATIVE_BUILD,true,500+i*200));}
 assert(rx.complete&&memcmp(rx.data,repeat_wave,320)==0);++checks;
 packet(p,repeat_wave,0);
 for(unsigned bit=0;bit<344;++bit){uint8_t bad[43];memcpy(bad,p,43);bad[bit/8]^=1U<<(bit%8);rpw_receiver r={};assert(!rpw_receive(&r,bad,RP_NATIVE_BUILD,true,500));++checks;}
 rpw_receiver stale={};assert(!rpw_receive(&stale,p,RP_NATIVE_BUILD,false,500));++checks;
 assert(!rpw_receive(&stale,p,RP_NATIVE_BUILD-1,true,500));++checks;
 assert(rpw_peer_reset(&rx,RP_NATIVE_BUILD,RP_NATIVE_BUILD,100,1,20)&&!rx.complete);++checks;
 bw_receiver snaprx={};for(unsigned i=0;i<BW_PAGES;++i){bw_packet(p,repeat_snap,2,i);assert(bw_receive(&snaprx,p,RP_NATIVE_BUILD,true,100+i*200));}
 assert(snaprx.complete[2]&&memcmp(snaprx.data[2],repeat_snap,92)==0&&!snaprx.complete[0]);++checks;
 mb_record empty={},boot=mb_next(&empty,RP_NATIVE_BUILD,MB_BOR);mb_confirm_clear(&boot,0);
 uint8_t boot_packet[43];mb_packet(boot_packet,&boot,2050);
 rpm_packet(p,&mic_repeat_state,3,boot.crc);assert(rpm_valid(p,RP_NATIVE_BUILD,true));++checks;
 uint8_t meta[43];memcpy(meta,p,43);
 for(unsigned bit=0;bit<344;++bit){uint8_t bad[43];memcpy(bad,meta,43);bad[bit/8]^=1U<<(bit%8);assert(!rpm_valid(bad,RP_NATIVE_BUILD,true));++checks;}
 first();fail_abort=true;mic_repeat_capture_arm(2000);assert(mic_repeat_state.state==RP_ERROR&&mic_bkin_record_ready&&!LL_TIM_IsEnabledAllOutputs(TIM1));++checks;
 first();fail_start=true;mic_repeat_capture_arm(2000);assert(mic_repeat_state.state==RP_ERROR&&mic_bkin_record_ready);++checks;
 first();fail_gpio=true;mic_repeat_capture_arm(2000);assert(mic_repeat_state.state==RP_ERROR);++checks;
 first();race_start=true;mic_repeat_capture_arm(2000);mic_bkin_prepare_record();assert(mic_repeat_state.state==RP_ERROR&&!mic_repeat_wave_ready&&mic_after_clear_break.magic==MIC_BREAK_MAGIC);++checks;
 reset();mic_repeat_capture_arm(2000);assert(mic_repeat_state.state==RP_FIRST_PENDING&&aborts==0);++checks;
 first();tim1.BDTR|=0x8000;mic_repeat_capture_arm(2000);assert(mic_repeat_state.state==RP_WAIT&&aborts==0);++checks;
 first();mic_repeat_capture_arm(2000);fake_tick=2020;channel.CNDTR=6144;tim1.SR=128;mic_break_capture_first(2020);
 fake_tick=2200;mic_bkin_prepare_record();assert(mic_repeat_wave_ready&&bp_record_valid(mic_repeat_wave)&&(bp_u32(mic_repeat_wave+20)&BP_DMA_ERROR));++checks;
 printf("{\"checks\":%u,\"meta_hex\":\"",checks);for(unsigned i=0;i<43;++i)printf("%02x",meta[i]);printf("\",\"first_wave\":\"");
 for(unsigned i=0;i<320;++i)printf("%02x",first_wave[i]);printf("\",\"boot_packet\":\"");for(unsigned i=0;i<43;++i)printf("%02x",boot_packet[i]);
 printf("\",\"repeat_wave\":\"");for(unsigned i=0;i<320;++i)printf("%02x",repeat_wave[i]);
 printf("\",\"repeat_snapshot\":\"");for(unsigned i=0;i<92;++i)printf("%02x",repeat_snap[i]);puts("\"}");
}
