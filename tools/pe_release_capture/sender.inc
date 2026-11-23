static void mic_send_encoder_release_page(uint32_t now_ms){
  static uint32_t last_ms;static uint8_t page,slot;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||!uno_link.link_seen||(uint32_t)(now_ms-last_ms)<150U||
      (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME];
  if(mic_encoder_release_packet(packet,slot,page)){
    if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)!=HAL_OK)return;
    last_ms=now_ms;
  }
  if(++page==PR_PAGES){page=0;slot^=1U;}
}
