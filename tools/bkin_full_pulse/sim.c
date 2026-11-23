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
typedef struct { uint32_t IDR; } gpio_t;
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
  DMA_PDATAALIGN_WORD=2,DMA_MDATAALIGN_WORD=2,DMA_CIRCULAR=1,DMA_PRIORITY_LOW=0,
  HAL_OK=0,RCC_HCLK_DIV1=1,DMA2_Channel1_IRQn=1,GPIO_PIN_6=64 };
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
volatile uint32_t mic_bkin_ring[MIC_BKIN_SAMPLE_COUNT];
volatile uint32_t mic_bkin_capture_state,mic_bkin_remaining,mic_bkin_dma_flags,
  mic_bkin_event_tick_ms,mic_bkin_record_ready;
uint8_t mic_bkin_record[MIC_BKIN_RECORD_BYTES];
uint32_t mic_bkin_record_crc;
#define MIC_BKIN_DMA_ACK(mask) do { dma.IFCR=(mask);dma.ISR&=~(mask); } while(0)
#include "firmware.inc"
static unsigned cases;
static void reset(void) {
  memset(&timer,0,sizeof(timer));memset(&channel,0,sizeof(channel));memset(&dma,0,sizeof(dma));
  memset((void*)mic_bkin_ring,0,sizeof(mic_bkin_ring));
  mic_bkin_capture_state=0;mic_bkin_record_ready=0;mic_bkin_dma_initialized=false;
  sim_tick=0;sim_hz=170000000;sim_clock_div=1;
  mic_bkin_capture_start(); assert(timer.ARR==169 && timer.PSC==0);
  dma.ISR=0;dma.IFCR=0;
}
static void step(uint32_t count,bool high,bool service) {
  if (mic_bkin_capture_state!=MIC_BKIN_RUNNING) return;
  mic_bkin_ring[(count-1)&1023]=high?64:0;
  channel.CNDTR=1024-(count&1023); sim_tick=count/1000;
  if (!(count&511)) {
    dma.ISR|=(count&512)?4:2;
    if (service) { DMA2_Channel1_IRQHandler(); dma.ISR&=~dma.IFCR;dma.IFCR=0; }
  }
}
static void dump(const char *name) {
  mic_bkin_prepare_record(); assert(mic_bkin_record_ready);
  assert(bp_record_valid(mic_bkin_record));
  char path[256];snprintf(path,sizeof(path),"%s.bin",name);
  FILE *f=fopen(path,"wb");assert(f);assert(fwrite(mic_bkin_record,1,320,f)==320);fclose(f);
}
static void packet(uint8_t *p,unsigned page) {
  memset(p,0,UV3_FRAME);p[0]=0x55;p[1]=0xaa;p[2]=0xd2;p[3]=(uint8_t)page;p[4]=14;
  bw_put32(p+6,BW_NUCLEO_BUILD);bw_put32(p+10,mic_bkin_record_crc);
  unsigned off=page*24,n=320-off;if(n>24)n=24;
  memcpy(p+14,mic_bkin_record+off,n);uv3_seal(p);
}
static void receiver_tests(void) {
  bkw_receiver rx={0};uint8_t p[UV3_FRAME];
  for(unsigned i=14;i>0;--i) { packet(p,i-1);assert(bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,20*(14-i))); }
  assert(rx.complete && !memcmp(rx.data,mic_bkin_record,320));
  memset(&rx,0,sizeof(rx));packet(p,0);p[15]^=1;
  assert(!bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,1));assert(!rx.complete);
  packet(p,0);assert(!bkw_receive(&rx,p,BW_NUCLEO_BUILD,false,2));
  assert(!bkw_receive(&rx,p,BW_NUCLEO_BUILD-1,true,3));
  assert(bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,4));
  p[20]^=1;uv3_seal(p);assert(!bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,5));
  memset(&rx,0,sizeof(rx));
  for(unsigned i=0;i<14;++i) { packet(p,i);assert(bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,i?6000+20*i:0)); }
  assert(!rx.complete); // timed-out page zero cannot mix with later pages
  packet(p,0);assert(bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,6400));assert(rx.complete);
  // Record CRC is required independently of per-frame CRC.
  memset(&rx,0,sizeof(rx));
  for(unsigned i=0;i<14;++i) { packet(p,i);if(i==2) {p[20]^=1;uv3_seal(p);} (void)bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,20*i); }
  assert(!rx.complete);
  // Last-page reserved bytes must be zero, even with valid CRC.
  memset(&rx,0,sizeof(rx));packet(p,13);p[37]=1;uv3_seal(p);
  assert(!bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,0));
  ++cases;
}
static void invalid_record_tests(void) {
  uint8_t original[320];memcpy(original,mic_bkin_record,320);
  const uint32_t original_crc=mic_bkin_record_crc;
  const unsigned offsets[]={4,20,24,28,32,36,40,44,48,52,56,60,64,68,312};
  const uint32_t values[]={2,0,65,100065,33,0,BP_UNKNOWN,99,0,16,1025,1,2,0,1};
  for(unsigned j=0;j<sizeof(offsets)/sizeof(*offsets);++j) {
    memcpy(mic_bkin_record,original,320);bw_put32(mic_bkin_record+offsets[j],values[j]);
    assert(!bp_record_valid(mic_bkin_record));
    mic_bkin_record_crc=uv3_crc32c(mic_bkin_record,320);
    bkw_receiver rx={0};uint8_t p[UV3_FRAME];
    for(unsigned i=0;i<14;++i) {packet(p,i);(void)bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,20*i);}
    assert(!rx.complete);
    ++cases;
  }
  memcpy(mic_bkin_record,original,320);mic_bkin_record_crc=original_crc;
}
static void pulse(unsigned start,unsigned width,const char *name) {
  reset();
  for(unsigned i=1;i<start+width+3000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,!(i>=start && i<start+width),true);
    if(i==start+2) mic_bkin_capture_trigger_from_break(sim_tick);
  }
  if (!(mic_bkin_pulse.flags&BP_POST_DONE) || bp_width(&mic_bkin_pulse)!=width) {
    fprintf(stderr,"pulse start=%u width=%u actual=%u flags=%u fall=%u rise=%u samples=%u trigger=%u\n",start,width,bp_width(&mic_bkin_pulse),mic_bkin_pulse.flags,mic_bkin_pulse.fall,mic_bkin_pulse.rise,mic_bkin_pulse.samples,mic_bkin_pulse.trigger);
    abort();
  }
  dump(name);receiver_tests();++cases;
}
int main(void) {
  const unsigned widths[]={1,24,70,511,1024,2500,90000};
  const unsigned phases[]={0,1,63,510,511,512,1022,1023};
  for(unsigned w=0;w<7;++w)for(unsigned p=0;p<8;++p) {
    char name[64];snprintf(name,sizeof(name),"pulse_%u_%u",widths[w],phases[p]);
    pulse(2048+phases[p],widths[w],name);
  }
  invalid_record_tests();
  reset();
  for(unsigned i=1;i<105000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,i<2050,true);if(i==2052)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  assert(mic_bkin_pulse.flags&BP_TIMEOUT);assert(bp_width(&mic_bkin_pulse)==BP_UNKNOWN);dump("timeout");++cases;
  reset();
  for(unsigned i=1;i<2000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,i>100,true);if(i==5)mic_bkin_capture_trigger_from_break(0);
  }
  assert(mic_bkin_pulse.flags&BP_LEFT);assert(mic_bkin_pulse.flags&BP_RISE);assert(bp_width(&mic_bkin_pulse)==BP_UNKNOWN);dump("left");++cases;
  reset();
  for(unsigned i=1;i<3000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,true,true);if(i==2052)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  assert(mic_bkin_pulse.flags&BP_NO_LOW);dump("no_low");++cases;
  reset();
  for(unsigned i=1;i<=3072;++i) {
    step(i,i<2050,i<2048);if(i==2052)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  DMA2_Channel1_IRQHandler();assert(mic_bkin_pulse.flags&BP_OVERRUN);dump("overrun");++cases;
  reset();mic_bkin_capture_trigger_from_break(0);dma.ISR=8;DMA2_Channel1_IRQHandler();
  assert(mic_bkin_pulse.flags&BP_DMA_ERROR);dump("dma_error");++cases;
  reset();mic_bkin_capture_trigger_from_break(0);sim_tick=111;mic_bkin_prepare_record();
  assert(mic_bkin_pulse.flags&BP_DMA_ERROR);dump("stalled");++cases;
  reset();
  for(unsigned i=1;i<3000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,i<2050?true:(i&1),true);if(i==2052)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  assert(mic_bkin_pulse.flags&BP_OVERFLOW);dump("overflow");++cases;
  // 32-bit sample-counter rollover: trigger coordinate still uses modular differences.
  reset();mic_bkin_completed=0xfffffe00U;mic_bkin_has_history=1;
  for(uint32_t i=0xfffffe01U;i!=1500U && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,!(i<40U || i>0xfffffff0U),true);
    if(i==2U)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  assert(bp_width(&mic_bkin_pulse)==55U);dump("counter_wrap");++cases;
  // First event is immutable, including after later triggers and START attempts.
  uint32_t crc=mic_bkin_record_crc;mic_bkin_capture_trigger_from_break(12345);mic_bkin_capture_start();mic_bkin_prepare_record();
  assert(crc==mic_bkin_record_crc);++cases;
  printf("{\"host_cases\":%u,\"pass\":true}\n",cases);
  return 0;
}
