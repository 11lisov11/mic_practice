#include "peer_epoch.h"
#include "encoder_health_wire.h"
#include "current_wire.h"
#include "peak_wire.h"
#include "zero_wire.h"
#include <cassert>
#include <cstdio>
#include <cstring>
static pe_records g_encoder_records;
static pe_history g_encoder_history;
[[maybe_unused]] static eh_receiver g_encoder_health;
static bw_receiver g_break_wire;
static bkw_receiver g_bkin_wave;
static urw_receiver g_uart_reject;
static ct_receiver g_current;
static pc_receiver g_peak;
static zh_receiver g_zero_history;
void dispatch(uint32_t previous_build,uint32_t g_bp_fw_build,uint16_t previous_good,uint16_t g_bp_good_cnt,uint32_t previous_age){
  if (bkw_peer_reset(&g_bkin_wave,previous_build,g_bp_fw_build,previous_good,g_bp_good_cnt,previous_age))
    {
      pe_reset(&g_encoder_history,&g_encoder_records);
      memset(&g_encoder_health,0,sizeof(g_encoder_health));
      bw_reset(&g_break_wire);urw_reset(&g_uart_reject);ct_reset(&g_current);pc_reset(&g_peak);zh_reset(&g_zero_history);
    }

}
int main(int argc,char**argv){
  assert(argc==2);FILE*f=fopen(argv[1],"rb");assert(f);uint8_t raw[WC_BYTES];assert(fread(raw,1,WC_BYTES,f)==WC_BYTES);fclose(f);
  memcpy(g_encoder_records.wire.bytes,raw,WC_BYTES);g_encoder_records.wire.valid=true;g_encoder_records.wire.crc=uv3_crc32c(raw,WC_BYTES);
  g_current.has_quality=true;g_current.quality[10]=42;
  dispatch(WC_PEER,WC_PEER,60000,3,20);
  assert(!g_current.has_quality); // Existing branch invalidates the fallback's old timestamp.

  assert(!g_encoder_records.wire.valid&&g_encoder_history.epoch==1&&g_encoder_history.previous_valid);
  assert(g_encoder_history.previous.wire.crc==uv3_crc32c(raw,WC_BYTES));
  assert(!memcmp(g_encoder_history.previous.wire.bytes,raw,WC_BYTES));
  dispatch(WC_PEER,WC_PEER,3,4,20);assert(g_encoder_history.epoch==1);
  dispatch(WC_PEER,WC_PEER,4,5,301);assert(g_encoder_history.epoch==2&&g_encoder_history.previous_valid);
  assert(!memcmp(g_encoder_history.previous.wire.bytes,raw,WC_BYTES));
  // A new complete waveform after reset must be accepted, not rejected as immutable old data.
  raw[32]^=1;
  for(unsigned page=0;page<WC_PAGES;page++){
    uint8_t packet[43];wc_frame(packet,page,uv3_crc32c(raw,WC_BYTES));
    unsigned off=page*24,n=WC_BYTES-off;if(n>24)n=24;memcpy(packet+14,raw+off,n);uv3_seal(packet);
    assert(wc_receive(&g_encoder_records.wire,packet,WC_PEER,true));
  }assert(g_encoder_records.wire.valid&&!memcmp(g_encoder_records.wire.bytes,raw,WC_BYTES));

  puts("{\"passed\":true}");
}
