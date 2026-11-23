
#include <cstdio>
#include <cstdlib>
#include "current_wire.h"
static ct_receiver g_current;
static urw_receiver g_uart_reject;
static bool g_bp_mcsdk_telemetry=true,g_pwm_enabled=false;
static uint32_t g_bp_last_rsp_ms=1000,g_bp_fw_build=CT_PEER_BUILD,g_bp_status=0;
static uint32_t millis(){return 1010;}
static unsigned checks;
static void check(bool okay){++checks;if(!okay){fprintf(stderr,"mixed wire %u failed\n",checks);exit(1);}}
static void dispatch(const uint8_t *buf) {for(unsigned once=0;once<1;++once){
      if(buf[2]==CT_SUMMARY || buf[2]==CT_DETAIL || buf[2]==CT_QUALITY) {
        const uint32_t observed_ms=millis();
        const bool fresh=g_bp_mcsdk_telemetry && (uint32_t)(observed_ms-g_bp_last_rsp_ms)<300U;
        (void)ct_receive(&g_current,buf,g_bp_fw_build,fresh,observed_ms);continue;
      }
      if(buf[2]==URW_VERSION) {
        const uint32_t observed_ms=millis();
        const bool fresh_off=g_bp_mcsdk_telemetry && !g_pwm_enabled &&
            (g_bp_status&0x22U)==0U && (uint32_t)(observed_ms-g_bp_last_rsp_ms)<300U;
        (void)urw_receive(&g_uart_reject,buf,g_bp_fw_build,fresh_off,observed_ms);continue;
      }

}}

int main() {
 ct_reset(&g_current);urw_reset(&g_uart_reject);
 uv3_rx input={};input.fatal_reject_valid=true;input.fatal_reject.meta[1]=UV3_BAD_CRC;
 uint8_t record[UR_BYTES];ur_serialize(record,&input,CT_PEER_BUILD);
 check(ur_record_valid(record,CT_PEER_BUILD));
 const uint32_t crc=uv3_crc32c(record,UR_BYTES);
 uint8_t p[UV3_FRAME];
 for(unsigned page=0;page<URW_PAGES;++page) {
  memset(p,0,sizeof(p));p[0]=0x55;p[1]=0xaa;p[2]=URW_VERSION;p[3]=page;p[4]=URW_PAGES;
  ur_put32(p+6,CT_PEER_BUILD);ur_put32(p+10,crc);
  unsigned start=page*URW_CHUNK,n=UR_BYTES-start;if(n>URW_CHUNK)n=URW_CHUNK;
  memcpy(p+14,record+start,n);uv3_seal(p);dispatch(p);
  check(g_uart_reject.good_pages==page+1);check(g_uart_reject.bad_pages==0);
  memset(p,0,sizeof(p));p[0]=0x55;p[1]=0xaa;p[2]=CT_SUMMARY;p[4]=page+1;p[38]=1;
  ur_put32(p+6,CT_PEER_BUILD);uv3_seal(p);dispatch(p);
  check(g_current.good==page+1);check(g_current.bad==0);
 }
 check(g_uart_reject.complete);check(memcmp(record,g_uart_reject.data,UR_BYTES)==0);
 memset(p,0,sizeof(p));p[0]=0x55;p[1]=0xaa;p[2]=CT_DETAIL;p[4]=15;p[38]=1;
 ur_put32(p+6,CT_PEER_BUILD);uv3_seal(p);dispatch(p);
 check(g_current.has_detail && g_current.good==15);
 p[25]^=1;dispatch(p);check(g_current.bad==1);
 check(g_uart_reject.complete && g_uart_reject.bad_pages==0);
 printf("{\"passed\":true,\"checks\":%u,\"uart_record_pages\":14}",checks);
}
