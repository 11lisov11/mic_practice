/* The production RX ISR/ring and TX DMA implementation are reused verbatim.
 * CRC-valid payloads are observed, never dispatched to a motor command. */
static uint32_t io_rx_bytes,io_rx_frames,io_rx_bad,io_rx_hardware,io_last_frame;
static uint32_t io_uart_flags,io_last_tx;
static void mic_combined_uart_poll(void){
 if(uno_tx_watchdog()!=HAL_OK)io_uart_flags|=1U;
 if(uno_rx_errors || uno_rx_overflow){io_rx_hardware=uno_rx_errors|(uno_rx_overflow?256U:0U);io_uart_flags|=2U;}
 uint8_t byte,marks;
 while(uno_rx_pop(&byte,&marks)){
  ++io_rx_bytes;
  uv3_result r=uv3_byte(&uno_transport,byte,marks,HAL_GetTick());
  if(r==UV3_READY){
   ++io_rx_frames;io_last_frame=HAL_GetTick();uno_link.last_seq=uno_transport.frame[5];
   uv3_commit(&uno_transport,HAL_GetTick(),false,false,false);
  }else if(r!=UV3_WAIT && r!=UV3_DROPPED){++io_rx_bad;io_uart_flags|=4U;}
 }
 uv3_result r=uv3_tick(&uno_transport,HAL_GetTick());
 if(r!=UV3_WAIT && r!=UV3_DROPPED){++io_rx_bad;io_uart_flags|=4U;}
 const uint32_t now=HAL_GetTick();
 if((uint32_t)(now-io_last_tx)>=20U && (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)<=1U){
  /* Existing43-byte sensor telemetry: gives real UART/DMA/TC load at50Hz.
   * This diagnostic identity is not enabled as a motor-control peer. */
  uint8_t packet[UV3_FRAME];mic_encoder_packet(packet,MIC_NUCLEO_FW_BUILD_ID);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)!=HAL_OK)io_uart_flags|=8U;
  else io_last_tx=now;
 }
}
void mic_io_uart_snapshot(uint32_t *v){
 v[0]=io_rx_bytes;v[1]=io_rx_hardware;v[2]=io_rx_frames;v[3]=io_rx_bad;v[4]=uno_rx_overflow;
 v[5]=mic_uart_tx.queued;v[6]=mic_uart_tx.completed;v[7]=mic_uart_tx.timeouts;
 v[8]=mic_uart_tx.dma_errors;v[9]=mic_uart_tx.full_errors;v[10]=mic_uart_tx.active;
 v[11]=USART1->CR1;v[12]=USART1->ISR;v[13]=io_last_frame;v[14]=uno_transport.fault;v[15]=io_uart_flags;
}
