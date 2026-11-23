static uint8_t mic_uart_reject_record[UR_BYTES];
static uint32_t mic_uart_reject_crc;
static bool mic_uart_reject_ready;
static void mic_uart_reject_packet(uint8_t *packet,unsigned page) {
  if(!mic_uart_reject_ready) {
    ur_serialize(mic_uart_reject_record,&uno_transport,MIC_NUCLEO_FW_BUILD_ID);
    mic_uart_reject_crc=uv3_crc32c(mic_uart_reject_record,UR_BYTES);mic_uart_reject_ready=true;
  }
  memset(packet,0,UV3_FRAME);packet[0]=0x55;packet[1]=0xaa;packet[2]=UR_VERSION;
  packet[3]=(uint8_t)page;packet[4]=UR_PAGES;
  ur_put32(packet+6,MIC_NUCLEO_FW_BUILD_ID);ur_put32(packet+10,mic_uart_reject_crc);
  unsigned offset=page*24U,n=UR_BYTES-offset;if(n>24)n=24;
  memcpy(packet+14,mic_uart_reject_record+offset,n);uv3_seal(packet);
}
