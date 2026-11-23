#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdint>
namespace baseline{

static const unsigned UV3_FRAME=43,UNO_TX_SLOTS=4,UNO_TX_TAG_DIAG=0,UNO_TX_TAG_OFF=2;
static const unsigned USART_CR1_TCIE=64,USART_CR3_DMAT=128,USART_ICR_TCCF=1,UART_FLAG_TC=64;
static const unsigned DMA_CCR_EN=1,DMA_CCR_TCIE=2,DMA_CCR_TEIE=8,HAL_ERROR=1;
struct Regs{uint32_t CR1=0,CR3=0,ICR=0,ISR=0,TDR=0;};static Regs uart;
struct HU{Regs*Instance;};static HU huart1={&uart};
struct DM{uint32_t CCR=0,CPAR=0,CMAR=0,CNDTR=0;};static DM channel,*DMA1_Channel1=&channel;
struct DC{uint32_t ISR=0,IFCR=0;};static DC dm,*DMA1=&dm;
static unsigned off_calls;static int tim;static int*TIM1=&tim;
static void LL_TIM_DisableAllOutputs(int*){++off_calls;}
static void __DMB(){}
static unsigned HAL_GetTick(){return 100;}
struct TX{uint32_t head,tail,active,started_ms,late_reported,hard_error,queued,completed,timeouts,full_errors,dma_errors,last_status,early_tc;uint8_t bytes[4][43],tags[4];};
static TX mic_uart_tx;static bool mic_last_control_reply_safe_off;
#define MIC_FOC_IRQ_SCOPE
#define MIC_FOC_IRQ_SCOPE_NAMED(a,b)
#define MIC_UART_TX_DMA_ACK(mask) do{DMA1->ISR&=~(mask);DMA1->IFCR=(mask);}while(0)
void DMA1_Channel1_IRQHandler(void);
static void reset(){mic_uart_tx={};uart={};channel={};dm={};off_calls=0;mic_last_control_reply_safe_off=false;
 mic_uart_tx.head=1;mic_uart_tx.tags[0]=UNO_TX_TAG_OFF;for(unsigned i=0;i<43;++i)mic_uart_tx.bytes[0][i]=(uint8_t)(17*i);}

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
  MIC_FOC_IRQ_SCOPE;
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
}
namespace candidate{

static const unsigned UV3_FRAME=43,UNO_TX_SLOTS=4,UNO_TX_TAG_DIAG=0,UNO_TX_TAG_OFF=2;
static const unsigned USART_CR1_TCIE=64,USART_CR3_DMAT=128,USART_ICR_TCCF=1,UART_FLAG_TC=64;
static const unsigned DMA_CCR_EN=1,DMA_CCR_TCIE=2,DMA_CCR_TEIE=8,HAL_ERROR=1;
struct Regs{uint32_t CR1=0,CR3=0,ICR=0,ISR=0,TDR=0;};static Regs uart;
struct HU{Regs*Instance;};static HU huart1={&uart};
struct DM{uint32_t CCR=0,CPAR=0,CMAR=0,CNDTR=0;};static DM channel,*DMA1_Channel1=&channel;
struct DC{uint32_t ISR=0,IFCR=0;};static DC dm,*DMA1=&dm;
static unsigned off_calls;static int tim;static int*TIM1=&tim;
static void LL_TIM_DisableAllOutputs(int*){++off_calls;}
static void __DMB(){}
static unsigned HAL_GetTick(){return 100;}
struct TX{uint32_t head,tail,active,started_ms,late_reported,hard_error,queued,completed,timeouts,full_errors,dma_errors,last_status,early_tc;uint8_t bytes[4][43],tags[4];};
static TX mic_uart_tx;static bool mic_last_control_reply_safe_off;
#define MIC_FOC_IRQ_SCOPE
#define MIC_FOC_IRQ_SCOPE_NAMED(a,b)
#define MIC_UART_TX_DMA_ACK(mask) do{DMA1->ISR&=~(mask);DMA1->IFCR=(mask);}while(0)
void DMA1_Channel1_IRQHandler(void);
static void reset(){mic_uart_tx={};uart={};channel={};dm={};off_calls=0;mic_last_control_reply_safe_off=false;
 mic_uart_tx.head=1;mic_uart_tx.tags[0]=UNO_TX_TAG_OFF;for(unsigned i=0;i<43;++i)mic_uart_tx.bytes[0][i]=(uint8_t)(17*i);}

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
  /* DMA TC owns the transition to UART TC. No UART TC interrupt while
     bytes remain in memory, even if the peripheral sees an inter-byte gap. */
  DMA1_Channel1->CCR |= DMA_CCR_EN|DMA_CCR_TEIE|DMA_CCR_TCIE;
  huart1.Instance->CR3 |= USART_CR3_DMAT;
  /* TCIE is enabled only by the final DMA transfer-complete IRQ. */
}
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
    ++mic_uart_tx.early_tc;
    /* Never clear TC here: a higher IRQ could have delayed this branch until
       after the final stop bit. DMA TC will arm TCIE and observe that level. */
    huart1.Instance->CR1 &= ~USART_CR1_TCIE;return;
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
  MIC_FOC_IRQ_SCOPE_NAMED(1,DMA1_Channel1_IRQn);
  const uint32_t flags=DMA1->ISR&0x0fU;
  MIC_UART_TX_DMA_ACK(flags);
  if(!(flags&8U)) {
    if((flags&2U) && mic_uart_tx.active && !mic_uart_tx.hard_error &&
       DMA1_Channel1->CNDTR==0U) {
      /* Last byte is now owned by UART. If its stop bit already left while
         this IRQ was delayed, the pending TC level immediately requests IRQ. */
      huart1.Instance->CR1 |= USART_CR1_TCIE;
    }
    return;
  }
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
}

int main(){
 baseline::reset();baseline::uno_tx_begin_locked(100);
 baseline::uart.ISR=baseline::UART_FLAG_TC;
 for(unsigned i=0;i<100;++i)baseline::uno_tx_tc_isr();
 assert(baseline::mic_uart_tx.early_tc==100&&(baseline::uart.CR1&baseline::USART_CR1_TCIE));
 unsigned scenarios=0;
 for(unsigned delay=0;delay<1024;++delay){
  candidate::reset();candidate::uno_tx_begin_locked(100);
  auto bytes=candidate::mic_uart_tx;candidate::uart.ISR=candidate::UART_FLAG_TC;
  assert(!(candidate::uart.CR1&candidate::USART_CR1_TCIE));
  for(unsigned i=0;i<100;++i)candidate::uno_tx_tc_isr();
  assert(!candidate::mic_uart_tx.early_tc&&!candidate::mic_uart_tx.completed);
  // A spurious/legacy early TC is disabled, never acknowledged as a frame end.
  candidate::uart.CR1|=candidate::USART_CR1_TCIE;candidate::uno_tx_tc_isr();
  assert(candidate::mic_uart_tx.early_tc==1&&!(candidate::uart.CR1&candidate::USART_CR1_TCIE));
  assert(candidate::mic_uart_tx.active&&candidate::mic_uart_tx.tail==0);
  candidate::channel.CNDTR=0;candidate::dm.ISR=2;
  // Simulate DMA IRQ arriving either before or after the final UART stop bit.
  candidate::uart.ISR=delay&1?candidate::UART_FLAG_TC:0;
  candidate::DMA1_Channel1_IRQHandler();
  assert(candidate::uart.CR1&candidate::USART_CR1_TCIE);
  candidate::uno_tx_tc_isr();
  if(!(delay&1)){assert(!candidate::mic_uart_tx.completed);candidate::uart.ISR=candidate::UART_FLAG_TC;candidate::uno_tx_tc_isr();}
  assert(candidate::mic_uart_tx.completed==1&&candidate::mic_uart_tx.tail==1&&!candidate::mic_uart_tx.active);
  candidate::uno_tx_tc_isr();assert(candidate::mic_uart_tx.completed==1);
  assert(!memcmp(bytes.bytes,candidate::mic_uart_tx.bytes,sizeof(bytes.bytes))&&candidate::mic_last_control_reply_safe_off);
  // Real DMA error keeps the original hard error/output disable and no restart.
  candidate::reset();candidate::uno_tx_begin_locked(100);candidate::dm.ISR=10;
  candidate::DMA1_Channel1_IRQHandler();
  assert(candidate::mic_uart_tx.hard_error&&candidate::mic_uart_tx.dma_errors==1&&candidate::off_calls==1);
  assert(!candidate::mic_uart_tx.completed&&!(candidate::uart.CR1&candidate::USART_CR1_TCIE));
  ++scenarios;
 }
 printf("{\"old_pending_TC_reentry_reproduced\":100,\"new_TX_event_scenarios\":%u,\"CRC_payload_unchanged\":true,\"DMA_error_still_stops\":true}\n",scenarios);
}
