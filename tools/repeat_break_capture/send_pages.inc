mic_send_break_page(uint32_t now_ms) {
  static uint32_t last_ms;
  static uint8_t slot;
  mic_bkin_prepare_record();
  if(!mic_last_control_reply_safe_off||uno_link.command_enabled||mic_break_start_window!=0U||
     LL_TIM_IsEnabledAllOutputs(TIM1)||MC_GetSTMStateMotor1()==RUN||(uint32_t)(now_ms-last_ms)<200U)return;
  last_ms=now_ms;
  const unsigned waves=3U*BW_PAGES, rejects=waves+MIC_BKIN_WIRE_PAGES;
  const unsigned repeats=rejects+UR_PAGES,total=repeats+MIC_BKIN_WIRE_PAGES;
  uint8_t packet[UV3_FRAME];bool send=false;
  if(slot>=repeats){
    if(mic_repeat_wave_ready){mic_repeat_wave_packet(packet,slot-repeats);send=true;}
  }else if(slot>=rejects){
    if(uno_transport.fatal_reject_valid){mic_uart_reject_packet(packet,slot-rejects);send=true;}
  }else if(slot>=waves){
    if(mic_bkin_record_ready){mic_bkin_wave_packet(packet,slot-waves);send=true;}
  }else{
    const unsigned kind=slot/BW_PAGES,page=slot%BW_PAGES;
    const volatile mic_break_snapshot_t *record=kind==0?&mic_first_break:kind==1?&mic_first_start_break:&mic_after_clear_break;
    uint8_t raw[BW_BYTES]={0};
    if(record->magic==MIC_BREAK_MAGIC){
      __DMB();const volatile uint8_t *bytes=(const volatile uint8_t*)record;
      for(unsigned i=0;i<BW_BYTES;++i)raw[i]=bytes[i];
    }
    bw_packet(packet,raw,kind,page);send=true;
  }
  if(send&&uno_tx_submit(packet,UNO_TX_TAG_DIAG)!=HAL_OK)bw_increment(&mic_break_diag_tx_errors);
  slot=(uint8_t)((slot+1U)%total);
}
