static void uno_transport_result(uv3_result result) {
  if (result == UV3_WAIT) return;
  if (result != UV3_READY) {
    const uint8_t reason = result == UV3_BAD_CRC ? UNO_DIAG_CRC :
        result == UV3_BAD_VERSION ? UNO_DIAG_VERSION : result == UV3_BAD_SEQUENCE ? UNO_DIAG_REPLAY :
        result == UV3_LINK_TIMEOUT || result == UV3_FRAME_TIMEOUT ? UNO_DIAG_TIMEOUT : UNO_DIAG_UART;
    uno_capture_diagnostics(reason, uno_transport.last_uart_flags, 0U);
    uno_link.last_bad_reason = reason;
    uno_link.last_uart_errors = uno_transport.last_uart_flags;
    uno_saturating_increment(&uno_link.bad_count);
    const uint8_t code = result == UV3_BAD_CRC ? UNO_FAULT_BAD_CRC :
        result == UV3_LINK_TIMEOUT || result == UV3_FRAME_TIMEOUT ? UNO_FAULT_TIMEOUT : UNO_FAULT_INTERNAL;
    uno_latch_fault_reason(code, reason);
    return;
  }
  if (uno_abort_pending_rx_fault()) return;
  uno_handle_valid_frame(uno_transport.frame);
  uno_send_reply();
  bool clean_clear = uno_transport.frame[3] == UNO_FLAG_CLEAR_FAULT &&
                     uno_transport.frame[4] == UNO_MODE_OFF;
  for (unsigned i = 6U; i < UV3_PAYLOAD; ++i) clean_clear = clean_clear && uno_transport.frame[i] == 0U;
  uv3_commit(&uno_transport, HAL_GetTick(),
             uno_link.command_enabled && MC_GetSTMStateMotor1() == RUN,
             uno_link.fault_latched, clean_clear);
}

static void uno_consume_sample(uint8_t byte, uint8_t flags) {
  uno_transport_result(uv3_byte(&uno_transport, byte, flags, HAL_GetTick()));
}
