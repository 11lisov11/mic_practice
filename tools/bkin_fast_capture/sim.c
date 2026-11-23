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
  DMA_PDATAALIGN_WORD=2,DMA_MDATAALIGN_HALFWORD=1,DMA_CIRCULAR=1,DMA_PRIORITY_LOW=0,
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
volatile uint16_t mic_bkin_ring[MIC_BKIN_SAMPLE_COUNT];
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
  mic_bkin_capture_start(); assert(timer.ARR==33 && timer.PSC==0);
  assert(hdma_mic_bkin.Init.PeriphDataAlignment==DMA_PDATAALIGN_WORD);
  assert(hdma_mic_bkin.Init.MemDataAlignment==DMA_MDATAALIGN_HALFWORD);
  assert(sizeof(mic_bkin_ring)==16384);
  dma.ISR=0;dma.IFCR=0;
}
static void step(uint32_t count,bool high,bool service) {
  if (mic_bkin_capture_state!=MIC_BKIN_RUNNING) return;
  mic_bkin_ring[(count-1)&8191]=high?64:0;
  channel.CNDTR=8192-(count&8191); sim_tick=count/5000;
  if (!(count&4095)) {
    dma.ISR|=(count&4096)?4:2;
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
static void peer_reset_tests(void) {
  bkw_receiver rx={0}; uint8_t p[UV3_FRAME];
  for (unsigned i=0;i<14;++i) {packet(p,i);assert(bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,i));}
  assert(rx.complete);
  assert(!bkw_peer_reset(&rx,BW_NUCLEO_BUILD,BW_NUCLEO_BUILD,10,11,20));
  assert(rx.complete); ++cases;
  assert(!bkw_peer_reset(&rx,BW_NUCLEO_BUILD,BW_NUCLEO_BUILD,65535,65535,20));
  assert(rx.complete); ++cases;
  assert(bkw_peer_reset(&rx,BW_NUCLEO_BUILD,BW_NUCLEO_BUILD,100,0,20));
  assert(!rx.complete && !rx.mask && !rx.received_ms); ++cases;
  packet(p,0);assert(bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,20));assert(rx.mask);
  assert(bkw_peer_reset(&rx,BW_NUCLEO_BUILD,BW_NUCLEO_BUILD,0,1,301));
  assert(!rx.mask); ++cases;
  assert(bkw_peer_reset(&rx,BW_NUCLEO_BUILD-2,BW_NUCLEO_BUILD,0,1,0)); ++cases;
  /* Deliver a genuinely different record after reboot, never the old cache. */
  const uint32_t old_tick=bw_u32(mic_bkin_record+12),old_crc=mic_bkin_record_crc;
  bw_put32(mic_bkin_record+12,old_tick+10000);mic_bkin_record_crc=uv3_crc32c(mic_bkin_record,320);
  packet(p,0);assert(!bkw_receive(&rx,p,BW_NUCLEO_BUILD,false,30));
  for(unsigned i=0;i<14;++i) {packet(p,i);assert(bkw_receive(&rx,p,BW_NUCLEO_BUILD,true,40+i));}
  assert(rx.complete && bw_u32(rx.data+12)==old_tick+10000); ++cases;
  bw_put32(mic_bkin_record+12,old_tick);mic_bkin_record_crc=old_crc;
}
static uint32_t rng=0x1541ac8fU;
static uint32_t random_value(void) { rng=1664525U*rng+1013904223U;return rng; }
static void span_equivalence_tests(void) {
  for(unsigned n=0;n<256;++n) {
    bp_capture scalar,span;bp_init(&scalar);bp_init(&span);
    scalar.trigger=span.trigger=random_value()%(BP_PRE+1);
    for(unsigned r=0;r<60 && !(scalar.flags&BP_FROZEN);++r) {
      uint32_t high=random_value()>>31;
      uint32_t count=1+random_value()%((n&1)?50000:400);
      uint32_t consumed=0;
      while(consumed<count && !(scalar.flags&BP_FROZEN)) {bp_feed(&scalar,high);++consumed;}
      assert(bp_feed_span(&span,high,count)==consumed);
      assert(!memcmp(&scalar,&span,sizeof(scalar)));
    }
    ++cases;
  }
  bp_capture a,b;bp_init(&a);bp_init(&b);a.trigger=b.trigger=2048;
  for(unsigned i=0;i<10;++i)bp_feed(&a,1);
  assert(bp_feed_span(&b,1,10)==10);
  for(unsigned i=0;i<BP_LIMIT+BP_PRE-10;++i)bp_feed(&a,0);
  assert(bp_feed_span(&b,0,UINT32_MAX)==BP_LIMIT+BP_PRE-10);
  assert(!memcmp(&a,&b,sizeof(a)) && (b.flags&BP_TIMEOUT));++cases;
}
static void invalid_record_tests(void) {
  uint8_t original[320];memcpy(original,mic_bkin_record,320);
  const uint32_t original_crc=mic_bkin_record_crc;
  const unsigned offsets[]={4,20,24,28,32,36,40,44,48,52,56,60,64,68,312};
  const uint32_t values[]={2,0,2049,502049,33,0,BP_UNKNOWN,99,0,16,8193,1,2,0,1};
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
  for(unsigned i=1;i<start+width+20000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,!(i>=start && i<start+width),true);
    if(i==start+2) mic_bkin_capture_trigger_from_break(sim_tick);
  }
  if (!(mic_bkin_pulse.flags&BP_POST_DONE) || bp_width(&mic_bkin_pulse)!=width) {
    fprintf(stderr,"pulse start=%u width=%u actual=%u flags=%u fall=%u rise=%u samples=%u trigger=%u\n",start,width,bp_width(&mic_bkin_pulse),mic_bkin_pulse.flags,mic_bkin_pulse.fall,mic_bkin_pulse.rise,mic_bkin_pulse.samples,mic_bkin_pulse.trigger);
    abort();
  }
  dump(name);receiver_tests();++cases;
}
static void delayed_pulse(unsigned delay,const char *name) {
  reset();const unsigned start=20000,width=5;
  for(unsigned i=1;i<start+delay+20000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,!(i>=start && i<start+width),true);
    if(i==start+delay)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  if(delay<BP_PRE) {
    assert(bp_width(&mic_bkin_pulse)==width && (mic_bkin_pulse.flags&BP_POST_DONE));
  } else {
    assert(bp_width(&mic_bkin_pulse)==BP_UNKNOWN && (mic_bkin_pulse.flags&BP_NO_LOW));
  }
  dump(name);++cases;
}
int main(void) {
  span_equivalence_tests();
  const unsigned widths[]={1,2,5,120,350,511,1024,2500,93480,450000};
  const unsigned phases[]={0,1,2047,4094,4095,4096,8190,8191};
  for(unsigned w=0;w<10;++w)for(unsigned p=0;p<8;++p) {
    char name[64];snprintf(name,sizeof(name),"pulse_%u_%u",widths[w],phases[p]);
    pulse(16384+phases[p],widths[w],name);
  }
  invalid_record_tests();
  peer_reset_tests();
  delayed_pulse(500,"delay_100us");
  delayed_pulse(1800,"delay_360us");
  delayed_pulse(3000,"delay_outside_history");
  reset();
  for(unsigned i=1;i<530000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,i<16386,true);if(i==16388)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  assert(mic_bkin_pulse.flags&BP_TIMEOUT);assert(bp_width(&mic_bkin_pulse)==BP_UNKNOWN);dump("timeout");++cases;
  reset();
  for(unsigned i=1;i<10000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,i>100,true);if(i==5)mic_bkin_capture_trigger_from_break(0);
  }
  assert(mic_bkin_pulse.flags&BP_LEFT);assert(mic_bkin_pulse.flags&BP_RISE);assert(bp_width(&mic_bkin_pulse)==BP_UNKNOWN);dump("left");++cases;
  reset();
  for(unsigned i=1;i<30000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,true,true);if(i==16388)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  assert(mic_bkin_pulse.flags&BP_NO_LOW);dump("no_low");++cases;
  reset();
  for(unsigned i=1;i<=24576;++i) {
    step(i,i<16386,i<16384);if(i==16388)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  DMA2_Channel1_IRQHandler();assert(mic_bkin_pulse.flags&BP_OVERRUN);dump("overrun");++cases;
  reset();mic_bkin_capture_trigger_from_break(0);dma.ISR=8;DMA2_Channel1_IRQHandler();
  assert(mic_bkin_pulse.flags&BP_DMA_ERROR);dump("dma_error");++cases;
  reset();mic_bkin_capture_trigger_from_break(0);sim_tick=111;mic_bkin_prepare_record();
  assert(mic_bkin_pulse.flags&BP_DMA_ERROR);dump("stalled");++cases;
  reset();
  for(unsigned i=1;i<30000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
    step(i,i<16386?true:(i&1),true);if(i==16388)mic_bkin_capture_trigger_from_break(sim_tick);
  }
  assert(mic_bkin_pulse.flags&BP_OVERFLOW);dump("overflow");++cases;
  // 32-bit sample-counter rollover: trigger coordinate still uses modular differences.
  reset();mic_bkin_completed=0xfffff000U;mic_bkin_has_history=1;
  for(uint32_t i=0xfffff001U;i!=10000U && mic_bkin_capture_state==MIC_BKIN_RUNNING;++i) {
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
