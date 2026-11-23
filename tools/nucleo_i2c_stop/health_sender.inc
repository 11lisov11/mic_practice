static void mic_send_encoder_health_page(uint32_t now_ms){
  static uint32_t last_ms,values[14];static uint8_t page,gen;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)){page=0;return;}
  if(!uno_link.link_seen || (uint32_t)(now_ms-last_ms)<250U ||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || mic_uart_tx.hard_error)return;
  if(!page){mic_encoder_health_snapshot(values);++gen;}
  uint8_t packet[UV3_FRAME];eh_packet(packet,values,page,gen);
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK){last_ms=now_ms;page^=1U;}
}
