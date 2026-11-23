/* Host executable: actual firmware recorder + receiver, mocked registers only. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "bkin_wave_capture.h"
#include "pulse_core.h"
#include "bkin_wave_wire.h"
typedef struct { uint32_t CR1,CR2,DIER,PSC,ARR,CNT,EGR,SR; } timer_t;
typedef struct { uint32_t CCR,CNDTR; } channel_t;
typedef struct { uint32_t ISR,IFCR; } dma_t;
typedef struct { uint32_t IDR,MODER,PUPDR; } gpio_t;
static timer_t timer;
static channel_t channel;
static dma_t dma;
static gpio_t gpio;
#define TIM2 (&timer)
#define DMA2_Channel1 (&channel)
#define DMA2 (&dma)
#define GPIOA (&gpio)
typedef struct {
  channel_t *Instance;
  struct { uint32_t Request,Direction,PeriphInc,MemInc,PeriphDataAlignment,
    MemDataAlignment,Mode,Priority; } Init;
} DMA_HandleTypeDef;
typedef struct { uint32_t APB1CLKDivider; } RCC_ClkInitTypeDef;
enum { TIM_DIER_UDE=256,TIM_CR1_CEN=1,TIM_CR2_MMS=112,TIM_EGR_UG=1,
  DMA_CCR_HTIE=4,DMA_CCR_TCIE=2,DMA_CCR_TEIE=8,DMA_REQUEST_TIM2_UP=1,
  DMA_PERIPH_TO_MEMORY=0,DMA_PINC_DISABLE=0,DMA_MINC_ENABLE=1,
  DMA_PDATAALIGN_WORD=2,DMA_MDATAALIGN_HALFWORD=1,DMA_CIRCULAR=1,DMA_PRIORITY_LOW=0,
  HAL_OK=0,RCC_HCLK_DIV1=1,DMA2_Channel1_IRQn=1,GPIO_PIN_6=64,GPIO_PIN_4=16,GPIO_MODE_INPUT=0,GPIO_NOPULL=0 };
static uint32_t sim_tick,sim_hz=170000000,sim_clock_div=1;
#define __HAL_RCC_TIM2_CLK_ENABLE() ((void)0)
#define __HAL_DMA_DISABLE(h) ((h)->Instance->CCR&=~1U)
#define __DSB() ((void)0)
#define __DMB() ((void)0)
static int HAL_DMA_Init(DMA_HandleTypeDef *h) { (void)h;return 0; }
static int HAL_DMA_Start(DMA_HandleTypeDef *h,uint32_t from,uint32_t to,uint32_t n) {
  (void)from;(void)to;h->Instance->CNDTR=n;h->Instance->CCR=1;return 0;
}
static void HAL_RCC_GetClockConfig(RCC_ClkInitTypeDef *c,uint32_t *l) { c->APB1CLKDivider=sim_clock_div;*l=0; }
static uint32_t HAL_RCC_GetPCLK1Freq(void) { return sim_hz; }
static uint32_t HAL_GetTick(void) { return sim_tick; }
static void HAL_NVIC_SetPriority(int a,int b,int c) { assert(a==1&&b==5&&c==0); }
static void HAL_NVIC_ClearPendingIRQ(int a) { (void)a; }
static void HAL_NVIC_EnableIRQ(int a) { (void)a; }
static void HAL_NVIC_DisableIRQ(int a) { (void)a; }
static DMA_HandleTypeDef hdma_mic_bkin;
volatile uint16_t mic_bkin_ring[MIC_BKIN_SAMPLE_COUNT];
volatile uint32_t mic_bkin_capture_state,mic_bkin_remaining,mic_bkin_dma_flags,
  mic_bkin_event_tick_ms,mic_bkin_record_ready;
uint8_t mic_bkin_record[MIC_BKIN_RECORD_BYTES];
uint32_t mic_bkin_record_crc;
#define MIC_BKIN_DMA_ACK(mask) do { dma.IFCR=(mask);dma.ISR&=~(mask); } while(0)
typedef struct {uint32_t Pin,Mode,Pull;} GPIO_InitTypeDef;
static bool sim_bad_gpio;
static void HAL_GPIO_Init(gpio_t *g,GPIO_InitTypeDef *p) {
  assert(g==GPIOA && p->Pin==16 && p->Mode==0 && p->Pull==0);
  g->MODER=sim_bad_gpio?256:0;g->PUPDR=0;
}
#define MIC_NUCLEO_FW_BUILD_ID 2026102102UL
#include "firmware.inc"
static unsigned cases;
static void reset(void) {
  memset(&timer,0,sizeof(timer));memset(&channel,0,sizeof(channel));memset(&dma,0,sizeof(dma));
  memset(&gpio,0,sizeof(gpio));
  memset((void*)mic_bkin_ring,0,sizeof(mic_bkin_ring));
  mic_bkin_capture_state=0;mic_bkin_record_ready=0;mic_bkin_dma_initialized=false;
  sim_tick=0;sim_hz=170000000;sim_clock_div=1;sim_bad_gpio=false;
  mic_bkin_capture_start();
  assert(timer.ARR==33 && timer.PSC==0 && mic_bkin_capture_state==MIC_BKIN_RUNNING);
  assert(hdma_mic_bkin.Init.PeriphDataAlignment==DMA_PDATAALIGN_WORD);
  assert(hdma_mic_bkin.Init.MemDataAlignment==DMA_MDATAALIGN_HALFWORD);
  assert(sizeof(mic_bkin_ring)==16384 && gpio.MODER==0 && gpio.PUPDR==0);
  dma.ISR=0;dma.IFCR=0;
}
static void step(uint32_t count,uint32_t state,bool service) {
  if (mic_bkin_capture_state!=MIC_BKIN_RUNNING) return;
  /* Unrelated port bits must not leak into either observation. */
  mic_bkin_ring[(count-1)&8191]=(uint16_t)(0xffafU | ((state&1)<<6) | (((state>>1)&1)<<4));
  channel.CNDTR=8192-(count&8191);sim_tick=count/5000;
  if (!(count&4095)) {
    dma.ISR|=(count&4096)?4:2;
    if(service) {DMA2_Channel1_IRQHandler();dma.ISR&=~dma.IFCR;dma.IFCR=0;}
  }
}
static void dump(const char *name) {
  mic_bkin_prepare_record();assert(mic_bkin_record_ready);
  assert(bp_record_valid(mic_bkin_record));
  char path[256];snprintf(path,sizeof(path),"%s.bin",name);
  FILE *f=fopen(path,"wb");assert(f);assert(fwrite(mic_bkin_record,1,320,f)==320);fclose(f);
}
static void receiver_tests(void) {
  bkw_receiver rx={0};uint8_t p[UV3_FRAME];
  for(unsigned i=14;i>0;--i) {
    mic_bkin_wave_packet(p,i-1);assert(bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,20*(14-i)));
  }
  assert(rx.complete && !memcmp(rx.data,mic_bkin_record,320));
  memset(&rx,0,sizeof(rx));mic_bkin_wave_packet(p,0);p[15]^=1;
  assert(!bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,1));
  mic_bkin_wave_packet(p,0);assert(!bkw_receive(&rx,p,BW_NUCLEO_BUILD,false,2));
  assert(!bkw_receive(&rx,p,BW_NUCLEO_BUILD-1,true,3));
  memset(&rx,0,sizeof(rx));
  for(unsigned i=0;i<14;++i) {
    mic_bkin_wave_packet(p,i);
    if(i==2) {p[20]^=1;uv3_seal(p);}
    (void)bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,20*i);
  }
  assert(!rx.complete);
  memset(&rx,0,sizeof(rx));
  for(unsigned i=0;i<14;++i) {
    mic_bkin_wave_packet(p,i);
    assert(bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,i?6000+20*i:0));
  }
  assert(!rx.complete);
  mic_bkin_wave_packet(p,0);assert(bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,6400));assert(rx.complete);
  assert(bkw_peer_reset(&rx,BW_NUCLEO_BUILD,BW_NUCLEO_BUILD,100,0,20));
  assert(!rx.complete && !rx.mask);++cases;
}
static uint32_t rng=0x1541ac8fU;
static uint32_t random_value(void) {rng=1664525U*rng+1013904223U;return rng;}
static void span_tests(void) {
  for(unsigned n=0;n<1000;++n) {
    bp_capture scalar,span;bp_init(&scalar);bp_init(&span);
    scalar.trigger=span.trigger=random_value()%(BP_PRE+1);
    for(unsigned r=0;r<64 && !(scalar.flags&BP_FROZEN);++r) {
      uint32_t state=random_value()>>30;
      uint32_t count=1+random_value()%((n&1)?50000:400);
      uint32_t consumed=0;
      while(consumed<count && !(scalar.flags&BP_FROZEN)) {bp_feed(&scalar,state);++consumed;}
      assert(bp_feed_span(&span,state,count)==consumed);
      assert(!memcmp(&scalar,&span,sizeof(scalar)));
    }
    ++cases;
  }
}
static void pulse(unsigned start,unsigned width,int skew,unsigned mode,const char *name) {
  reset();
  const unsigned source_start=(unsigned)((int)start+skew);
  for(unsigned i=1;i<start+width+(unsigned)abs(skew)+20000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    bool a=!(mode&1) || !(i>=start && i<start+width);
    bool b=!(mode&2) || !(i>=source_start && i<source_start+width);
    step(i,(unsigned)a|((unsigned)b<<1),true);
    if(i==start+2) mic_bkin_capture_trigger_from_break(sim_tick);
  }
  assert(mic_bkin_pulse.flags== (BP_FROZEN|BP_POST_DONE));
  dump(name);receiver_tests();++cases;
}
int main(void) {
  span_tests();
  for(uint32_t i=0;i<65536;++i) assert(bp_state(i)==(((i>>6)&1)|(((i>>4)&1)<<1)));
  const unsigned widths[]={1,2,3,120,350,2500,93480,450000};
  const unsigned phases[]={0,1,2047,4094,4095,4096,8190,8191};
  for(unsigned w=0;w<8;++w) for(unsigned p=0;p<8;++p) {
    char name[64];snprintf(name,sizeof(name),"equal_%u_%u",widths[w],phases[p]);
    pulse(16384+phases[p],widths[w],0,3,name);
  }
  pulse(20000,3,0,1,"sink_only");pulse(20000,3,0,2,"source_only");
  pulse(20000,5,-2,3,"skew_source_first");pulse(20000,5,2,3,"skew_sink_first");
  pulse(20000,3,200,3,"late_source");pulse(20000,350,500,3,"late_source_100us");
  /* One line's long pulse must not be cut off by the other's early recovery. */
  reset();
  for(unsigned i=1;i<140000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,(i<20000||i>=20003?1U:0U)|(i<20000||i>=120000?2U:0U),true);
    if(i==20002) mic_bkin_capture_trigger_from_break(sim_tick);
  }
  dump("source_long");assert(mic_bkin_pulse.samples>100000);++cases;
  reset();
  for(unsigned i=1;i<540000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,i<20000?3U:1U,true);if(i==20002)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  dump("timeout");assert(mic_bkin_pulse.flags&BP_TIMEOUT);++cases;
  reset();
  for(unsigned i=1;i<10000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,i>100?3U:1U,true);if(i==5)mic_bkin_capture_trigger_from_break(0);
  }
  dump("left");++cases;
  reset();
  for(unsigned i=1;i<30000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,3U,true);if(i==20000)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  dump("no_low");++cases;
  reset();
  for(unsigned i=1;i<30000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,i<20000?3U:(i&1?1U:2U),true);
    if(i==20002)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  dump("overflow");assert(mic_bkin_pulse.flags&BP_OVERFLOW);++cases;
  reset();
  for(unsigned i=1;i<=16384;++i)step(i,3U,true);
  mic_bkin_capture_trigger_from_break(sim_tick);dma.ISR=6;DMA2_Channel1_IRQHandler();
  dump("overrun");assert(mic_bkin_pulse.flags&BP_OVERRUN);++cases;
  reset();for(unsigned i=1;i<=20000;++i)step(i,3U,true);
  mic_bkin_capture_trigger_from_break(sim_tick);dma.ISR=8;DMA2_Channel1_IRQHandler();
  dump("dma_error");assert(mic_bkin_pulse.flags&BP_DMA_ERROR);++cases;
  reset();for(unsigned i=1;i<=20000;++i)step(i,3U,true);
  mic_bkin_capture_trigger_from_break(sim_tick);sim_tick+=111;mic_bkin_prepare_record();
  dump("stalled");assert(mic_bkin_pulse.flags&BP_DMA_ERROR);++cases;
  reset();mic_bkin_capture_state=0;sim_bad_gpio=true;mic_bkin_capture_start();
  assert(mic_bkin_capture_state==MIC_BKIN_CAPTURE_ERROR);++cases;
  printf("{\"pass\":true,\"host_cases\":%u,\"gpio_values_checked\":65536}\n",cases);
}
