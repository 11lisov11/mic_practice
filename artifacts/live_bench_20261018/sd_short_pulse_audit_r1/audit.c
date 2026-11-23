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

static void wordstep(unsigned count,unsigned word) {
  if(mic_bkin_capture_state!=MIC_BKIN_RUNNING)return;
  mic_bkin_ring[(count-1)&8191]=(uint16_t)word;
  channel.CNDTR=8192-(count&8191);sim_tick=count/5000;
  if(!(count&4095)) {dma.ISR|=(count&4096)?4:2;DMA2_Channel1_IRQHandler();dma.ISR&=~dma.IFCR;dma.IFCR=0;}
}
static uint32_t random_word=0x7131;
static unsigned next_word(void) {random_word=1664525U*random_word+1013904223U;return random_word;}
static const bp_run observed[]={{1,115},{0,1},{1,51},{0,1},{1,312},{0,1},{1,117},{0,1},{1,141},{0,1},{1,170},{0,1},{1,193},{0,1},{1,2},{0,1},{1,256},{0,1},{1,171},{0,1},{1,139},{0,1},{1,53},{0,1},{1,117},{0,1},{1,140},{0,1},{1,53},{0,2},{1,323}};
int main(void) {
  for(unsigned phase=0;phase<8192;phase++) {
    reset();unsigned trigger=16384+phase;
    for(unsigned i=1;i<trigger+10000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;i++) {
      /* PA6 is always HIGH, every other stored input can change. */
      wordstep(i,next_word()|64U);
      if(i==trigger)mic_bkin_capture_trigger_from_break(sim_tick);
    }
    assert(mic_bkin_pulse.runs==1 && mic_bkin_pulse.run[0].level==1);
    assert(mic_bkin_pulse.flags==(BP_FROZEN|BP_POST_DONE|BP_NO_LOW));
    assert(bp_width(&mic_bkin_pulse)==BP_UNKNOWN);++cases;
  }
  for(unsigned phase=0;phase<8192;phase+=127) {
    reset();unsigned trigger=20000+phase,origin=trigger-2048+1;
    unsigned j=0,run=0,remaining=observed[0].count;
    for(unsigned i=1;i<trigger+10000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;i++) {
      unsigned high=1;
      if(i>=origin && j<2369) {
        high=observed[run].level;++j;
        if(!--remaining && run+1<sizeof(observed)/sizeof(*observed))remaining=observed[++run].count;
      }
      wordstep(i,(next_word()&~64U)|(high?64U:0));
      if(i==trigger)mic_bkin_capture_trigger_from_break(sim_tick);
    }
    assert(mic_bkin_pulse.samples==2369 && mic_bkin_pulse.flags==519);
    assert(mic_bkin_pulse.runs==sizeof(observed)/sizeof(*observed));
    assert(!memcmp(mic_bkin_pulse.run,observed,sizeof(observed)));
    assert(bp_width(&mic_bkin_pulse)==2);++cases;
  }
  const unsigned widths[]={120,350};
  for(unsigned w=0;w<2;w++)for(unsigned phase=0;phase<8192;phase+=127) {
    reset();unsigned start=20000+phase;
    for(unsigned i=1;i<start+10000 && mic_bkin_capture_state==MIC_BKIN_RUNNING;i++) {
      unsigned high=!(i>=start && i<start+widths[w]);
      wordstep(i,(next_word()&~64U)|(high?64U:0));
      if(i==start+2)mic_bkin_capture_trigger_from_break(sim_tick);
    }
    assert(bp_width(&mic_bkin_pulse)==widths[w]);
    assert(!(mic_bkin_pulse.flags&(BP_DMA_ERROR|BP_OVERRUN|BP_OVERFLOW)));++cases;
  }
  printf("{\"pass\":true,\"cases\":%u,\"constant_high_phases\":8192,\"observed_wave_replays\":65,\"long_pulse_replays\":130}\n",cases);
  return 0;
}
