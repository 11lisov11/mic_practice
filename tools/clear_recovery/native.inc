/* Immutable first valid CLEAR attempt per boot. Diagnostic only, OFF delivery. */
static uint8_t mic_clear_diag_packet[UV3_FRAME];
static uint8_t mic_clear_diag_ready;
static void mic_clear_diag_begin(void) {
 if(mic_clear_diag_ready)return;
 memset(mic_clear_diag_packet,0,sizeof(mic_clear_diag_packet));
 uint8_t *p=mic_clear_diag_packet;p[0]=0x55;p[1]=0xAA;p[2]=CC_WIRE;p[3]=1;
 cc_put32(p+6,MIC_NUCLEO_FW_BUILD_ID);cc_put32(p+10,HAL_GetTick());
 uno_tx_lock();
 cc_put32(p+14,mic_uart_tx.head);cc_put32(p+18,mic_uart_tx.tail);
 cc_put32(p+22,mic_uart_tx.started_ms);
 p[26]=(mic_uart_tx.active?1U:0U)|(mic_uart_tx.hard_error?2U:0U)|(mic_uart_tx.late_reported?4U:0U);
 uno_tx_unlock();
 p[26]|=((GPIOA->IDR&GPIO_PIN_6)?8U:0U)|((TIM1->DIER&TIM_DIER_BIE)?16U:0U)|
        (LL_TIM_IsEnabledAllOutputs(TIM1)?32U:0U);
 p[27]=uno_link.last_seq;cc_put32(p+28,TIM1->SR);
 uint16_t faults=MC_GetCurrentFaultsMotor1(),past=MC_GetOccurredFaultsMotor1();
 p[32]=(uint8_t)faults;p[33]=(uint8_t)(faults>>8);
 p[34]=(uint8_t)past;p[35]=(uint8_t)(past>>8);p[36]=(uint8_t)MC_GetSTMStateMotor1();
}
static void mic_clear_diag_finish(uint8_t result) {
 if(mic_clear_diag_ready)return;
 mic_clear_diag_packet[37]=result;uv3_seal(mic_clear_diag_packet);
 __DMB();mic_clear_diag_ready=1U;
}
static void mic_send_clear_page(uint32_t now_ms) {
 static uint32_t last_ms;
 if(!mic_clear_diag_ready || LL_TIM_IsEnabledAllOutputs(TIM1) || uno_link.command_enabled ||
    !mic_last_control_reply_safe_off || mic_uart_tx.hard_error ||
    (uint32_t)(mic_uart_tx.head-mic_uart_tx.tail)>1U || (uint32_t)(now_ms-last_ms)<500U)return;
 if(uno_tx_submit(mic_clear_diag_packet,UNO_TX_TAG_DIAG)==HAL_OK)last_ms=now_ms;
}
