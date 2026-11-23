#ifndef MIC_SD_TRACE_RECORDER_H
#define MIC_SD_TRACE_RECORDER_H
#include "sd_trace_wire.h"

/* Owns unused TIM2 + DMA1 channel1 + DMAMUX channel0. GPIO configuration,
   TIM1, ADC and all protection registers are read-only to this recorder. */
enum { MIC_SDT_PERIOD_CYCLES=85U };
typedef struct {
  volatile uint16_t ring[SDT_SAMPLES];
  uint8_t record[SDT_BYTES];
  volatile uint32_t initialized, running, frozen, published;
  volatile uint32_t clock_hz, start_ms, stop_ms, reason, flags;
  volatile uint32_t remaining, dma_flags, gpioa, tim1_af1, tim1_sr;
} mic_sd_trace_state_t;
extern mic_sd_trace_state_t mic_sd_trace;

static inline void mic_sd_trace_init(uint32_t timer_clock_hz) {
  __HAL_RCC_TIM2_CLK_ENABLE();
  __HAL_RCC_DMA1_CLK_ENABLE();
  __HAL_RCC_DMAMUX1_CLK_ENABLE();
  mic_sd_trace.clock_hz=timer_clock_hz;
  if ((TIM2->CR1&TIM_CR1_CEN) || (DMA1_Channel1->CCR&DMA_CCR_EN) ||
      DMAMUX1_Channel0->CCR!=0U || timer_clock_hz==0U) return;
#ifndef MIC_SD_TRACE_HOST_TEST
  const uintptr_t address=(uintptr_t)mic_sd_trace.ring;
  /* STM32G431: DMA-accessible SRAM1+SRAM2, not the CCM alias. */
  if (address<0x20000000U || address+sizeof(mic_sd_trace.ring)>0x20005800U) return;
#endif
  TIM2->CR1=0;TIM2->CR2=0;TIM2->SMCR=0;TIM2->DIER=0;
  TIM2->PSC=0;TIM2->ARR=MIC_SDT_PERIOD_CYCLES-1U;TIM2->CNT=0;
  TIM2->EGR=TIM_EGR_UG;TIM2->SR=0;
  DMA1_Channel1->CCR=0;
  DMA1_Channel1->CPAR=(uint32_t)(uintptr_t)&GPIOA->IDR;
  DMA1_Channel1->CMAR=(uint32_t)(uintptr_t)mic_sd_trace.ring;
  DMAMUX1_Channel0->CCR=DMA_REQUEST_TIM2_UP;
  DMA1_Channel1->CCR=DMA_CCR_MINC|DMA_CCR_CIRC|DMA_CCR_PSIZE_0|DMA_CCR_MSIZE_0;
  /* Low priority; no DMA/timer interrupts, no callbacks in the control path. */
  mic_sd_trace.initialized=1U;
}

static inline void mic_sd_trace_arm(uint32_t tick_ms) {
  /* Preserve the first actual protection event until reboot. Normal STOP
     captures may be replaced by the next explicit START. */
  if (mic_sd_trace.frozen && mic_sd_trace.reason==SDT_BREAK) return;
  mic_sd_trace.published=0;mic_sd_trace.frozen=0;
  mic_sd_trace.start_ms=tick_ms;mic_sd_trace.reason=0;
  if (!mic_sd_trace.initialized) {
    mic_sd_trace.reason=SDT_RESOURCE_ERROR;mic_sd_trace.flags=SDT_INIT_ERROR;
    mic_sd_trace.stop_ms=tick_ms;mic_sd_trace.remaining=SDT_SAMPLES;
    mic_sd_trace.frozen=1U;return;
  }
  TIM2->CR1&=~TIM_CR1_CEN;TIM2->DIER=0;
  DMA1_Channel1->CCR&=~DMA_CCR_EN;
  DMA1->IFCR=DMA_IFCR_CGIF1;
  DMA1_Channel1->CNDTR=SDT_SAMPLES;
  TIM2->CNT=0;TIM2->EGR=TIM_EGR_UG;TIM2->SR=0;
  mic_sd_trace.flags=SDT_READY;mic_sd_trace.running=1U;
  __DMB();
  DMA1_Channel1->CCR|=DMA_CCR_EN;
  TIM2->DIER=TIM_DIER_UDE;TIM2->CR1|=TIM_CR1_CEN;
}

static inline void mic_sd_trace_freeze(uint32_t reason,uint32_t tick_ms) {
  if (!mic_sd_trace.running) return;
  /* The hardware Break has already removed MOE. No loops, UART, HAL control
     calls, allocation, waiting or bulk copy in this bounded IRQ path. */
  TIM2->CR1&=~TIM_CR1_CEN;TIM2->DIER=0;
  DMA1_Channel1->CCR&=~DMA_CCR_EN;
  __DSB();
  const uint32_t first=DMA1_Channel1->CNDTR;
  const uint32_t status=DMA1->ISR;
  __DMB();
  mic_sd_trace.remaining=DMA1_Channel1->CNDTR;
  mic_sd_trace.dma_flags=status&15U;
  mic_sd_trace.flags=SDT_READY|((status&DMA_ISR_TCIF1)?SDT_WRAPPED:0U)|
      ((status&DMA_ISR_TEIF1)?SDT_DMA_ERROR:0U)|
      ((first!=mic_sd_trace.remaining)?SDT_UNSTABLE_COUNT:0U);
  mic_sd_trace.gpioa=GPIOA->IDR;mic_sd_trace.tim1_af1=TIM1->AF1;
  mic_sd_trace.tim1_sr=TIM1->SR;
  mic_sd_trace.reason=(mic_sd_trace.tim1_sr&0x180U)?SDT_BREAK:reason;
  mic_sd_trace.stop_ms=tick_ms;mic_sd_trace.running=0U;
  __DMB();mic_sd_trace.frozen=1U;
}

/* Only call after the control layer has confirmed outputs OFF. The DMA ring
   is immutable here; all scanning and packing stays out of the Break ISR. */
static inline void mic_sd_trace_publish_off(void) {
  if (!mic_sd_trace.frozen || mic_sd_trace.published) return;
  __DMB();
  uint8_t *p=mic_sd_trace.record;memset(p,0,SDT_BYTES);
  const uint32_t remaining=mic_sd_trace.remaining;
  uint32_t flags=mic_sd_trace.flags;
  if (remaining>SDT_SAMPLES) flags|=SDT_DMA_ERROR;
  const uint32_t written=remaining<=SDT_SAMPLES?SDT_SAMPLES-remaining:0U;
  const uint32_t count=(flags&SDT_INIT_ERROR)?0U:((flags&SDT_WRAPPED)?SDT_SAMPLES:written);
  const uint32_t first=(flags&SDT_WRAPPED)?written%SDT_SAMPLES:0U;
  const uint32_t values[16]={SDT_MAGIC,SDT_SCHEMA,SDT_BYTES,mic_sd_trace.stop_ms,
      mic_sd_trace.reason,flags,count,MIC_SDT_PERIOD_CYCLES,mic_sd_trace.clock_hz,
      remaining,mic_sd_trace.dma_flags,mic_sd_trace.gpioa,mic_sd_trace.tim1_af1,
      mic_sd_trace.tim1_sr,mic_sd_trace.start_ms,0U};
  for (unsigned i=0;i<16;++i) bw_put32(p+4U*i,values[i]);
  for (unsigned i=0;i<count;++i) {
    const uint16_t gpio=mic_sd_trace.ring[(first+i)%SDT_SAMPLES];
    p[SDT_HEADER+i/8]|=(uint8_t)(((gpio>>6)&1U)<<(i%8));
    p[SDT_HEADER+SDT_SAMPLES/8+i/8]|=(uint8_t)(((gpio>>8)&1U)<<(i%8));
  }
  __DMB();mic_sd_trace.published=1U;
}
#endif
