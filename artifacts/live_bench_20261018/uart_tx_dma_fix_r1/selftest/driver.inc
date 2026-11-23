/* USART1 TX owns DMA1 channel 1, DMAMUX request USART1_TX. RX stays IRQ.
   DMA2 ch1 remains SD; DMA2 ch2/ch3 remain MCSDK USART2 RX/TX. */
enum { UNO_TX_SLOTS=4U, UNO_TX_TAG_DIAG=0U, UNO_TX_TAG_ON=1U, UNO_TX_TAG_OFF=2U };
typedef struct {
  uint32_t head,tail,active,started_ms,late_reported,hard_error;
  uint32_t queued,completed,timeouts,full_errors,dma_errors,last_status,early_tc;
  uint8_t bytes[UNO_TX_SLOTS][UV3_FRAME];
  uint8_t tags[UNO_TX_SLOTS];
} uno_tx_state_t;
volatile uno_tx_state_t mic_uart_tx;
static DMA_HandleTypeDef hdma_uno_tx;
void DMA1_Channel1_IRQHandler(void);
#ifndef MIC_UART_TX_DMA_ACK
#define MIC_UART_TX_DMA_ACK(mask) (DMA1->IFCR=(mask))
#endif

static void uno_tx_lock(void) {
  HAL_NVIC_DisableIRQ(USART1_IRQn);
  HAL_NVIC_DisableIRQ(DMA1_Channel1_IRQn);
}
static void uno_tx_unlock(void) {
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);
  HAL_NVIC_EnableIRQ(USART1_IRQn);
}

static void uno_tx_begin_locked(uint32_t now_ms) {
  if(mic_uart_tx.active || mic_uart_tx.hard_error || mic_uart_tx.head==mic_uart_tx.tail) return;
  const unsigned slot=mic_uart_tx.tail&(UNO_TX_SLOTS-1U);
  huart1.Instance->CR1 &= ~USART_CR1_TCIE;
  huart1.Instance->CR3 &= ~USART_CR3_DMAT;
  DMA1_Channel1->CCR &= ~DMA_CCR_EN;
  MIC_UART_TX_DMA_ACK(0x0fU);
  huart1.Instance->ICR=USART_ICR_TCCF;
  DMA1_Channel1->CPAR=(uint32_t)(uintptr_t)&huart1.Instance->TDR;
  DMA1_Channel1->CMAR=(uint32_t)(uintptr_t)&mic_uart_tx.bytes[slot][0];
  DMA1_Channel1->CNDTR=UV3_FRAME;
  mic_uart_tx.started_ms=now_ms;
  mic_uart_tx.late_reported=0U;
  mic_uart_tx.active=1U;
  __DMB();
  DMA1_Channel1->CCR |= DMA_CCR_EN|DMA_CCR_TEIE;
  huart1.Instance->CR3 |= USART_CR3_DMAT;
  huart1.Instance->CR1 |= USART_CR1_TCIE;
}

static int uno_tx_submit(const uint8_t *frame,uint8_t tag) {
  int status=HAL_OK;
  uno_tx_lock();
  if(mic_uart_tx.hard_error) status=HAL_ERROR;
  else if((uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>=UNO_TX_SLOTS) {
    ++mic_uart_tx.full_errors;status=HAL_BUSY;
  } else {
    const unsigned slot=mic_uart_tx.head&(UNO_TX_SLOTS-1U);
    for(unsigned i=0;i<UV3_FRAME;++i) mic_uart_tx.bytes[slot][i]=frame[i];
    mic_uart_tx.tags[slot]=tag;
    __DMB();++mic_uart_tx.head;++mic_uart_tx.queued;
    uno_tx_begin_locked(HAL_GetTick());
  }
  uno_tx_unlock();
  return status;
}

/* Called after the unchanged RX/error drain, at the same IRQ priority 3.
   TC means the last stop bit left the UART, not just DMA memory copied. */
static void uno_tx_tc_isr(void) {
  if(!(huart1.Instance->CR1&USART_CR1_TCIE) || !(huart1.Instance->ISR&UART_FLAG_TC)) return;
  if(DMA1->ISR&8U) { DMA1_Channel1_IRQHandler();return; }
  huart1.Instance->ICR=USART_ICR_TCCF;
  if(!mic_uart_tx.active || mic_uart_tx.hard_error) {
    huart1.Instance->CR1 &= ~USART_CR1_TCIE;return;
  }
  if(DMA1_Channel1->CNDTR!=0U) {
    /* A delayed DMA request may leave an inter-byte idle. Never treat this
       as end of frame or advance to a new packet before all 43 bytes. */
    ++mic_uart_tx.early_tc;return;
  }
  huart1.Instance->CR1 &= ~USART_CR1_TCIE;
  huart1.Instance->CR3 &= ~USART_CR3_DMAT;
  DMA1_Channel1->CCR &= ~DMA_CCR_EN;
  MIC_UART_TX_DMA_ACK(0x0fU);
  const uint8_t tag=mic_uart_tx.tags[mic_uart_tx.tail&(UNO_TX_SLOTS-1U)];
  if(tag!=UNO_TX_TAG_DIAG) mic_last_control_reply_safe_off=(tag==UNO_TX_TAG_OFF);
  ++mic_uart_tx.tail;++mic_uart_tx.completed;mic_uart_tx.active=0U;
  uno_tx_begin_locked(HAL_GetTick());
}

void DMA1_Channel1_IRQHandler(void) {
  const uint32_t flags=DMA1->ISR&0x0fU;
  MIC_UART_TX_DMA_ACK(flags);
  if(!(flags&8U)) return;
  /* A real DMA bus error is fail-closed and never restarts half a packet.
     Do not call non-reentrant MCSDK routines from this ISR. */
  mic_uart_tx.hard_error=1U;
  ++mic_uart_tx.dma_errors;
  mic_uart_tx.last_status=HAL_ERROR;
  DMA1_Channel1->CCR &= ~DMA_CCR_EN;
  huart1.Instance->CR3 &= ~USART_CR3_DMAT;
  huart1.Instance->CR1 &= ~USART_CR1_TCIE;
  LL_TIM_DisableAllOutputs(TIM1);
}

static int uno_tx_watchdog(uint32_t now_ms) {
  int failure=HAL_OK;
  uno_tx_lock();
  if(mic_uart_tx.hard_error && !mic_uart_tx.late_reported) failure=HAL_ERROR;
  else if(mic_uart_tx.active && !mic_uart_tx.late_reported &&
      (uint32_t)(now_ms-mic_uart_tx.started_ms)>UNO_REPLY_TIMEOUT_MS) {
    ++mic_uart_tx.timeouts;failure=HAL_TIMEOUT;
  }
  if(failure!=HAL_OK) {
    mic_uart_tx.late_reported=1U;mic_uart_tx.last_status=(uint32_t)failure;
    /* Crucially, a wall-clock timeout does NOT abort DMA or change buffer,
       tail, CNDTR or TCIE. Main stops the motor; the current frame finishes. */
  }
  uno_tx_unlock();
  return failure;
}

static bool uno_tx_clear_ready(void) {
  return !mic_uart_tx.hard_error && !mic_uart_tx.active && mic_uart_tx.head==mic_uart_tx.tail;
}

static void uno_tx_init(void) {
  __HAL_RCC_DMA1_CLK_ENABLE();
  memset(&hdma_uno_tx,0,sizeof(hdma_uno_tx));
  hdma_uno_tx.Instance=DMA1_Channel1;
  hdma_uno_tx.Init.Request=DMA_REQUEST_USART1_TX;
  hdma_uno_tx.Init.Direction=DMA_MEMORY_TO_PERIPH;
  hdma_uno_tx.Init.PeriphInc=DMA_PINC_DISABLE;
  hdma_uno_tx.Init.MemInc=DMA_MINC_ENABLE;
  hdma_uno_tx.Init.PeriphDataAlignment=DMA_PDATAALIGN_BYTE;
  hdma_uno_tx.Init.MemDataAlignment=DMA_MDATAALIGN_BYTE;
  hdma_uno_tx.Init.Mode=DMA_NORMAL;
  hdma_uno_tx.Init.Priority=DMA_PRIORITY_HIGH;
  if(HAL_DMA_Init(&hdma_uno_tx)!=HAL_OK) Error_Handler();
  HAL_NVIC_SetPriority(DMA1_Channel1_IRQn,3U,0U);
  HAL_NVIC_ClearPendingIRQ(DMA1_Channel1_IRQn);
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);
}
