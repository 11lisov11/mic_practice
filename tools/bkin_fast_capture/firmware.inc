static bool mic_bkin_dma_initialized;
static volatile uint32_t mic_bkin_completed;
static volatile uint32_t mic_bkin_has_history;
static volatile uint32_t mic_bkin_cursor;
static volatile uint32_t mic_bkin_stream_error;
static volatile uint32_t mic_bkin_triggered;
static bp_capture mic_bkin_pulse;
#ifndef MIC_BKIN_DMA_ACK
#define MIC_BKIN_DMA_ACK(mask) (DMA2->IFCR=(mask))
#endif

static void mic_bkin_freeze(void) {
  TIM2->DIER &= ~TIM_DIER_UDE;
  TIM2->CR1 &= ~TIM_CR1_CEN;
  __HAL_DMA_DISABLE(&hdma_mic_bkin);
  __DSB();
  mic_bkin_remaining=DMA2_Channel1->CNDTR;
  mic_bkin_dma_flags=DMA2->ISR & 0x0FU;
  __DMB();
  mic_bkin_capture_state=MIC_BKIN_CAPTURED;
}

static void mic_bkin_capture_init(void) {
  if (mic_bkin_dma_initialized) return;
  __HAL_RCC_TIM2_CLK_ENABLE();
  memset(&hdma_mic_bkin,0,sizeof(hdma_mic_bkin));
  hdma_mic_bkin.Instance=DMA2_Channel1;
  hdma_mic_bkin.Init.Request=DMA_REQUEST_TIM2_UP;
  hdma_mic_bkin.Init.Direction=DMA_PERIPH_TO_MEMORY;
  hdma_mic_bkin.Init.PeriphInc=DMA_PINC_DISABLE;
  hdma_mic_bkin.Init.MemInc=DMA_MINC_ENABLE;
  hdma_mic_bkin.Init.PeriphDataAlignment=DMA_PDATAALIGN_WORD;
  /* GPIO is read as a word; DMA stores its low 16 bits, including PA6. */
  hdma_mic_bkin.Init.MemDataAlignment=DMA_MDATAALIGN_HALFWORD;
  hdma_mic_bkin.Init.Mode=DMA_CIRCULAR;
  hdma_mic_bkin.Init.Priority=DMA_PRIORITY_LOW;
  if (HAL_DMA_Init(&hdma_mic_bkin)!=HAL_OK) {
    mic_bkin_capture_state=MIC_BKIN_CAPTURE_ERROR; return;
  }
  mic_bkin_dma_initialized=true;
}

static void mic_bkin_capture_start(void) {
  /* Immutable first event per boot, including across STOP/CLEAR/START. */
  if (mic_bkin_capture_state!=MIC_BKIN_CAPTURE_IDLE) return;
  mic_bkin_capture_init();
  if (!mic_bkin_dma_initialized) return;
  RCC_ClkInitTypeDef clocks={0}; uint32_t latency=0;
  HAL_RCC_GetClockConfig(&clocks,&latency);
  uint32_t hz=HAL_RCC_GetPCLK1Freq();
  if (clocks.APB1CLKDivider!=RCC_HCLK_DIV1) hz*=2U;
  if (hz<2U*MIC_BKIN_SAMPLE_HZ || hz%MIC_BKIN_SAMPLE_HZ) {
    mic_bkin_capture_state=MIC_BKIN_CAPTURE_ERROR; return;
  }
  /* MCSDK's one-shot boot synchronization has finished. ARR must be nonzero. */
  TIM2->CR2 &= ~TIM_CR2_MMS;
  TIM2->CR1=0; TIM2->DIER=0; TIM2->PSC=0;
  TIM2->ARR=hz/MIC_BKIN_SAMPLE_HZ-1U;
  TIM2->CNT=0; TIM2->EGR=TIM_EGR_UG; TIM2->SR=0;
  MIC_BKIN_DMA_ACK(0x0FU);
  bp_init(&mic_bkin_pulse);
  mic_bkin_completed=0; mic_bkin_has_history=0; mic_bkin_triggered=0; mic_bkin_stream_error=0;
  if (HAL_DMA_Start(&hdma_mic_bkin,(uint32_t)(uintptr_t)&GPIOA->IDR,
      (uint32_t)(uintptr_t)mic_bkin_ring,MIC_BKIN_SAMPLE_COUNT)!=HAL_OK) {
    mic_bkin_capture_state=MIC_BKIN_CAPTURE_ERROR; return;
  }
  /* Lower priority than Break (4), PWM (0), ADC (2), UART (3). */
  HAL_NVIC_SetPriority(DMA2_Channel1_IRQn,5,0);
  HAL_NVIC_ClearPendingIRQ(DMA2_Channel1_IRQn);
  mic_bkin_capture_state=MIC_BKIN_RUNNING;
  DMA2_Channel1->CCR |= DMA_CCR_HTIE|DMA_CCR_TCIE|DMA_CCR_TEIE;
  HAL_NVIC_EnableIRQ(DMA2_Channel1_IRQn);
  TIM2->DIER=TIM_DIER_UDE; TIM2->CR1=TIM_CR1_CEN;
}

void mic_bkin_capture_trigger_from_break(uint32_t tick_ms) {
  if (mic_bkin_capture_state!=MIC_BKIN_RUNNING || mic_bkin_triggered) return;
  /* Constant-time publication only. DMA continues after hardware shutdown;
     no scanning, waiting, UART or MCSDK operations in the Break handler. */
  const uint32_t completed=mic_bkin_completed;
  const uint32_t next=(MIC_BKIN_SAMPLE_COUNT-DMA2_Channel1->CNDTR)&8191U;
  const uint32_t pending=(next-(completed&8191U))&8191U;
  const uint32_t pre=(mic_bkin_has_history || pending>=BP_PRE) ? BP_PRE : pending;
  mic_bkin_cursor=completed+pending-pre;
  mic_bkin_pulse.trigger=pre;
  mic_bkin_event_tick_ms=tick_ms;
  __DMB(); mic_bkin_triggered=1;
}

void DMA2_Channel1_IRQHandler(void) {
  const uint32_t flags=DMA2->ISR&0x0FU;
  if (mic_bkin_capture_state!=MIC_BKIN_RUNNING) { MIC_BKIN_DMA_ACK(0x0FU); return; }
  const uint32_t expected=(mic_bkin_completed&4096U) ? 2U : 4U;
  if ((flags&8U) || (flags&6U)==6U || !(flags&expected)) {
    mic_bkin_stream_error |= (flags&8U) ? BP_DMA_ERROR : BP_OVERRUN;
    MIC_BKIN_DMA_ACK(0x0FU);
    /* Discard ambiguous history rather than inventing samples. */
    const uint32_t next=(8192U-DMA2_Channel1->CNDTR)&8191U;
    mic_bkin_completed=(mic_bkin_completed&~8191U)+(next&~4095U);
  } else {
    MIC_BKIN_DMA_ACK(expected);
    mic_bkin_completed+=4096U;
    mic_bkin_has_history=1;
  }
  if (!mic_bkin_triggered) return;
  if (mic_bkin_stream_error) {
    bp_finish(&mic_bkin_pulse,mic_bkin_stream_error); mic_bkin_freeze(); return;
  }
  const uint32_t end=mic_bkin_completed;
  /* Break can preempt this lower-priority handler after its boundary was
     published. Its prehistory may then start in the still-writing half. */
  if ((int32_t)(end-mic_bkin_cursor)<0) return;
  if ((uint32_t)(end-mic_bkin_cursor)>8192U) {
    bp_finish(&mic_bkin_pulse,BP_OVERRUN); mic_bkin_freeze(); return;
  }
  /* At most 6144 samples at first service, then 4096. Coalesce constant
     levels instead of running the state machine for every sample. A later
     DMA boundary during this scan invalidates the trace conservatively. */
  while (mic_bkin_cursor!=end && !(mic_bkin_pulse.flags&BP_FROZEN)) {
    const uint32_t high=!!(mic_bkin_ring[mic_bkin_cursor&8191U]&GPIO_PIN_6);
    uint32_t count=1;
    while (count<(uint32_t)(end-mic_bkin_cursor) &&
        !!(mic_bkin_ring[(mic_bkin_cursor+count)&8191U]&GPIO_PIN_6)==high) ++count;
    mic_bkin_cursor+=bp_feed_span(&mic_bkin_pulse,high,count);
  }
  __DMB();
  if ((DMA2->ISR&8U) || (DMA2->ISR&6U)) {
    /* Another half completed during scanning: data may have been overwritten. */
    bp_finish(&mic_bkin_pulse,(DMA2->ISR&8U) ? BP_DMA_ERROR : BP_OVERRUN);
  }
  if (mic_bkin_pulse.flags&BP_FROZEN) mic_bkin_freeze();
}

static void mic_bkin_put32(uint8_t *p,uint32_t value) {
  p[0]=(uint8_t)value; p[1]=(uint8_t)(value>>8);
  p[2]=(uint8_t)(value>>16); p[3]=(uint8_t)(value>>24);
}
static void mic_bkin_prepare_record(void) {
  /* Wall-clock fallback if the sampling timer/DMA stops after the trigger. */
  if (mic_bkin_capture_state==MIC_BKIN_RUNNING && mic_bkin_triggered &&
      (uint32_t)(HAL_GetTick()-mic_bkin_event_tick_ms)>110U) {
    HAL_NVIC_DisableIRQ(DMA2_Channel1_IRQn);
    if (mic_bkin_capture_state==MIC_BKIN_RUNNING) {
      bp_finish(&mic_bkin_pulse,BP_TIMEOUT|BP_DMA_ERROR);
      mic_bkin_freeze();
    }
  }
  if (mic_bkin_capture_state!=MIC_BKIN_CAPTURED || mic_bkin_record_ready) return;
  __DMB();
  const uint32_t h[16]={MIC_BKIN_RECORD_MAGIC,4U,MIC_BKIN_RECORD_BYTES,
    mic_bkin_event_tick_ms,200U,mic_bkin_pulse.flags,
    mic_bkin_pulse.trigger,mic_bkin_pulse.samples,mic_bkin_pulse.runs,
    mic_bkin_pulse.fall,mic_bkin_pulse.rise,bp_width(&mic_bkin_pulse),
    BP_LIMIT,mic_bkin_dma_flags,mic_bkin_remaining,0U};
  memset(mic_bkin_record,0,sizeof(mic_bkin_record));
  for (unsigned i=0;i<16;++i) mic_bkin_put32(mic_bkin_record+4*i,h[i]);
  for (unsigned i=0;i<mic_bkin_pulse.runs;++i) {
    mic_bkin_put32(mic_bkin_record+64+8*i,mic_bkin_pulse.run[i].level);
    mic_bkin_put32(mic_bkin_record+68+8*i,mic_bkin_pulse.run[i].count);
  }
  mic_bkin_record_crc=uv3_crc32c(mic_bkin_record,MIC_BKIN_RECORD_BYTES);
  __DMB(); mic_bkin_record_ready=1;
}
