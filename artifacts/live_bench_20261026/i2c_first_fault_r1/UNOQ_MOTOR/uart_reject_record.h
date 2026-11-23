#ifndef MIC_UART_REJECT_RECORD_H
#define MIC_UART_REJECT_RECORD_H
#include "uart_v3_transport.h"
enum { UR_BYTES=320, UR_PAGES=14, UR_VERSION=0xD3 };
#define UR_MAGIC UINT32_C(0x31545255)
static inline void ur_put32(uint8_t *p,uint32_t x) {
  for(unsigned i=0;i<4;++i)p[i]=(uint8_t)(x>>(8*i));
}
static inline uint32_t ur_get32(const uint8_t *p) {
  return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static inline void ur_serialize(uint8_t *p,const uv3_rx *rx,uint32_t build) {
  memset(p,0,UR_BYTES);
  const uint32_t h[8]={UR_MAGIC,1,UR_BYTES,build,rx->last_reject_valid,
    rx->fatal_reject_valid,rx->speculative_expired,0};
  for(unsigned i=0;i<8;++i)ur_put32(p+4*i,h[i]);
  const uv3_reject *e[2]={&rx->last_reject,&rx->fatal_reject};
  for(unsigned k=0;k<2;++k) {
    if(!(k ? rx->fatal_reject_valid : rx->last_reject_valid))continue;
    uint8_t *q=p+32+144*k;
    for(unsigned i=0;i<14;++i)ur_put32(q+4*i,e[k]->meta[i]);
    memcpy(q+56,e[k]->bytes,44);memcpy(q+100,e[k]->marks,44);
  }
}
static inline bool ur_record_valid(const uint8_t *p,uint32_t build) {
  if(ur_get32(p)!=UR_MAGIC || ur_get32(p+4)!=1 || ur_get32(p+8)!=UR_BYTES ||
     ur_get32(p+12)!=build || ur_get32(p+16)>1 || ur_get32(p+20)!=1 || ur_get32(p+28))return false;
  for(unsigned k=0;k<2;++k) {
    const uint8_t *q=p+32+144*k;
    if(!ur_get32(p+16+4*k)) {
      for(unsigned i=0;i<144;++i)if(q[i])return false;
      continue;
    }
    uint32_t reason=ur_get32(q+4),n=ur_get32(q+8),prefix=ur_get32(q+12);
    if(reason<UV3_BAD_CRC || reason>UV3_BAD_SEQUENCE || n>UV3_FRAME || prefix>UV3_FRAME ||
        ur_get32(q+16)>15 || (ur_get32(q+20)>255 && ur_get32(q+20)!=UINT32_MAX) ||
        ur_get32(q+24)>UV3_NE_BUDGET || ur_get32(q+28)>UV3_NE_BUDGET || ur_get32(q+44)>3)return false;
    for(unsigned i=n;i<44;++i)if(q[56+i] || q[100+i])return false;
    for(unsigned i=0;i<n;++i)if(q[100+i]&~15U)return false;
    if(n==UV3_FRAME) {
      if(ur_get32(q+48)!=ur_get32(q+56+UV3_PAYLOAD) ||
         ur_get32(q+52)!=uv3_crc32c(q+56,UV3_PAYLOAD))return false;
    } else if(ur_get32(q+48) || ur_get32(q+52))return false;
  }
  return true;
}
#endif
