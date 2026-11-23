static void mic_send_bus_clear(uint32_t now_ms){
  static uint32_t last_ms;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||!uno_link.link_seen||(uint32_t)(now_ms-last_ms)<500U||
     (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(mic_encoder_bus_clear_packet(packet)&&uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)last_ms=now_ms;
}
