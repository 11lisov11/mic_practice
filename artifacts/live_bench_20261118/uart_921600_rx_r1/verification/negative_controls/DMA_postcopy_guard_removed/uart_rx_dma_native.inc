/* UART1 RX: DMA1 channel2/DMAMUX1 channel1, ring128. TX stays channel1,
 * BKIN stays DMA2ch1, MCSDK UART2 stays DMA2ch2/ch3. No motor priority changes.
 * IRQ ownership: USART1 and DMA1ch2 have equal priority3, one cursor writer.
 */
#include "uart_rx_dma_core.h"
static volatile uint8_t mic_uart_rx_dma[URD_BYTES];
urd_state mic_uart_rx_dma_diag;
static void uno_rx_dma_init(void){
 __HAL_RCC_DMA1_CLK_ENABLE();
 DMA1_Channel2->CCR=0;
 DMA1->IFCR=0xf0U;
 DMAMUX1_Channel1->CCR=DMA_REQUEST_USART1_RX;
 DMA1_Channel2->CPAR=(uint32_t)(uintptr_t)&huart1.Instance->RDR;
 DMA1_Channel2->CMAR=(uint32_t)(uintptr_t)mic_uart_rx_dma;
 DMA1_Channel2->CNDTR=URD_BYTES;
 memset(&mic_uart_rx_dma_diag,0,sizeof(mic_uart_rx_dma_diag));
 DMA1_Channel2->CCR=DMA_CCR_MINC|DMA_CCR_CIRC|DMA_CCR_PL_1|DMA_CCR_HTIE|DMA_CCR_TCIE|DMA_CCR_TEIE;
 HAL_NVIC_SetPriority(DMA1_Channel2_IRQn,3U,0U);
 HAL_NVIC_ClearPendingIRQ(DMA1_Channel2_IRQn);
 HAL_NVIC_EnableIRQ(DMA1_Channel2_IRQn);
 __DMB();DMA1_Channel2->CCR|=DMA_CCR_EN;
 huart1.Instance->CR3|=USART_CR3_DMAR;
}
static void uno_rx_dma_drain(void){
 uint32_t flags=0,remaining=0;unsigned stable=0;
 for(unsigned retry=0;retry<3;++retry){
  uint32_t before=DMA1->ISR&0xe0U;remaining=DMA1_Channel2->CNDTR;__DMB();flags=DMA1->ISR&0xe0U;
  if(before==flags){stable=1;break;}
 }
 if(!stable){++mic_uart_rx_dma_diag.retries;return;}
 unsigned bits=((flags&0x40U)?(unsigned)URD_HALF:0U)|((flags&0x20U)?(unsigned)URD_FULL:0U)|((flags&0x80U)?(unsigned)URD_ERROR:0U);
 urd_batch b=urd_plan(&mic_uart_rx_dma_diag,remaining,bits);
 if(b.result==URD_WAIT)return; /* CNDTR0/reload edge: keep pending flags. */
 DMA1->IFCR=flags; /* Never acknowledge a later boundary not in the snapshot. */
 if(b.result==URD_FAILED){
  uno_rx_errors|=UV3_ORE;
  /* Same immediate output-disable policy as an actual TX DMA bus error. */
  LL_TIM_DisableAllOutputs(TIM1);return;
 }
 if(b.result==URD_GAP){uno_rx_overflow=1U;return;}
 for(unsigned i=0;i<b.count;++i){
  uint8_t byte=mic_uart_rx_dma[(b.first+i)&(URD_BYTES-1U)];
  if(!uno_rx_errors&&!uno_rx_overflow&&!uno_rx_push(byte,0U))uno_rx_overflow=1U;
 }

}
void DMA1_Channel2_IRQHandler(void){
 MIC_FOC_IRQ_SCOPE_NAMED(2,DMA1_Channel2_IRQn);
 uno_rx_dma_drain();
}
/* DMA is the sole RDR owner. IDLE publishes short/partial43-byte bursts, HT/TC
 * service sustained input. Any PE/FE/NE/ORE is fatal to this batch: DMA cannot
 * attribute noise to one byte, so bounded-NE forgiveness is deliberately NOT
 * used here. Original CRC/sequence/watchdog/stop guards remain unchanged.
 */
void USART1_IRQHandler(void){
 MIC_FOC_IRQ_SCOPE_NAMED(2,USART1_IRQn);
 uint32_t status=huart1.Instance->ISR;
 uint32_t errors=status&(UART_FLAG_ORE|UART_FLAG_NE|UART_FLAG_FE|UART_FLAG_PE);
 uint8_t marks=((errors&UART_FLAG_PE)?(unsigned)UV3_PE:0U)|((errors&UART_FLAG_FE)?(unsigned)UV3_FE:0U)|
  ((errors&UART_FLAG_NE)?(unsigned)UV3_NE:0U)|((errors&UART_FLAG_ORE)?(unsigned)UV3_ORE:0U);
 if(marks)uno_rx_errors|=marks;
 if(errors)huart1.Instance->ICR=errors;
 if(status&UART_FLAG_IDLE)huart1.Instance->ICR=UART_CLEAR_IDLEF;
 uno_rx_dma_drain();
 uno_tx_tc_isr();
}
