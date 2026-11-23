static void mic_send_break_page(uint32_t now_ms) {
  static uint32_t last_ms;
  static uint8_t slot;
  if (uno_link.command_enabled || mic_break_start_window != 0U ||
      LL_TIM_IsEnabledAllOutputs(TIM1) || MC_GetSTMStateMotor1() == RUN ||
      (uint32_t)(now_ms-last_ms) < 200U) return;
  last_ms = now_ms;
  const unsigned kind = slot / BW_PAGES;
  const unsigned page = slot % BW_PAGES;
  const volatile mic_break_snapshot_t *record = kind == 0U ? &mic_first_break : &mic_first_start_break;
  uint8_t raw[BW_BYTES] = {0};
  if (record->magic == MIC_BREAK_MAGIC) {
    __DMB();
    const volatile uint8_t *bytes = (const volatile uint8_t *)record;
    for (unsigned i=0;i<BW_BYTES;++i) raw[i]=bytes[i];
  }
  uint8_t packet[UV3_FRAME];
  bw_packet(packet,raw,kind,page);
  /* A diagnostic TX failure is counted separately; normal control TX fault
     handling remains unchanged. No START/CLEAR or retry loop occurs here. */
  if (HAL_UART_Transmit(&huart1,packet,UV3_FRAME,UNO_REPLY_TIMEOUT_MS) != HAL_OK)
    bw_increment(&mic_break_diag_tx_errors);
  slot=(uint8_t)((slot+1U)%(2U*BW_PAGES));
}
