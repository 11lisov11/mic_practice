/* Repeat diagnostic never clears a fault, enables outputs, or changes BKE/BKF. */
static void mic_repeat_capture_arm(uint32_t tick_ms) {
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled)return;
  mic_bkin_prepare_record();
  const bool first_ready=mic_bkin_record_ready &&
    mic_first_break.magic==MIC_BREAK_MAGIC && mic_bkin_capture_state==MIC_BKIN_CAPTURED && !mic_repeat_active;
  if(!rp_request(&mic_repeat_state,first_ready,true,tick_ms,mic_break_irq_count,mic_bkin_record_crc))return;
  /* The frozen circular DMA is disabled, but HAL still owns it as BUSY.
   * Release only this diagnostic channel before reusing its ring. */
  HAL_NVIC_DisableIRQ(DMA2_Channel1_IRQn);
  if(hdma_mic_bkin.State==HAL_DMA_STATE_BUSY && HAL_DMA_Abort(&hdma_mic_bkin)!=HAL_OK){
    mic_repeat_state.state=RP_ERROR;return;
  }
  HAL_NVIC_ClearPendingIRQ(DMA2_Channel1_IRQn);
  mic_repeat_active=true;mic_bkin_capture_state=MIC_BKIN_CAPTURE_IDLE;
  mic_bkin_capture_start();
  if(mic_bkin_capture_state!=MIC_BKIN_RUNNING || mic_repeat_state.state!=RP_ARMED){
    if(mic_bkin_capture_state==MIC_BKIN_RUNNING)mic_bkin_freeze();
    mic_bkin_capture_state=MIC_BKIN_CAPTURE_ERROR;
    mic_repeat_state.state=RP_ERROR;
  }else mic_repeat_state.armed_tick=HAL_GetTick();
}

void mic_repeat_break_irq(uint32_t tick_ms,uint32_t sr) {
  if(!rp_claim(&mic_repeat_state,mic_break_irq_count,tick_ms))return;
  mic_break_capture_record(&mic_after_clear_break,tick_ms,sr);
  if(mic_bkin_capture_state!=MIC_BKIN_RUNNING || !mic_bkin_triggered)
    mic_repeat_state.state=RP_ERROR;
}

static void mic_send_repeat_meta(uint32_t now_ms) {
  static uint32_t last;
  if(LL_TIM_IsEnabledAllOutputs(TIM1)||uno_link.command_enabled||
     !mic_last_control_reply_safe_off||(uint32_t)(now_ms-last)<500U||
     (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U||mic_uart_tx.hard_error)return;
  uint8_t packet[UV3_FRAME],boot[UV3_FRAME];mic_boot_packet(boot,now_ms);
  const uint8_t flags=(mic_after_clear_break.magic==MIC_BREAK_MAGIC?1U:0U)|
    (mic_repeat_wave_ready?2U:0U);
  rpm_packet(packet,&mic_repeat_state,flags,rpm_u32(boot+30));
  if(uno_tx_submit(packet,UNO_TX_TAG_DIAG)==HAL_OK)last=now_ms;
}
