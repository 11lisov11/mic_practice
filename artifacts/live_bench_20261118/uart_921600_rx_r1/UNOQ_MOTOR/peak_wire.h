#ifndef MIC_ADC_PEAK_WIRE_H
#define MIC_ADC_PEAK_WIRE_H
#include "uart_v3_transport.h"
#include "current_wire.h"
#include <string.h>
enum { PC_WIRE=0xD8, PC_WIRE_BYTES=1024, PC_PAYLOAD=30, PC_PAGES=35 };
static_assert((int)PC_WIRE!=(int)CT_SUMMARY && (int)PC_WIRE!=(int)CT_DETAIL && (int)PC_WIRE!=(int)CT_QUALITY &&
              (int)PC_WIRE!=(int)URW_VERSION && (int)PC_WIRE!=(int)BKW_VERSION && (int)PC_WIRE!=(int)BW_VERSION &&
              (int)PC_WIRE!=(int)UV3_VERSION,"ADC peak pages need a unique wire version");
typedef struct {
  uint8_t data[PC_WIRE_BYTES];
  uint64_t pages;
  uint32_t good,bad,received_ms;
  bool complete;
} pc_receiver;
static inline void pc_reset(pc_receiver *r){memset(r,0,sizeof(*r));}
static inline uint32_t pcw_crc(const uint8_t *bytes) {
  uint32_t crc=0xffffffffUL;
  for(unsigned i=0;i<PC_WIRE_BYTES;++i) {
    crc^=(i>=60 && i<64)?0:bytes[i];
    for(unsigned j=0;j<8;++j)crc=(crc>>1)^((crc&1)?0x82f63b78UL:0);
  }
  return crc^0xffffffffUL;
}
static inline bool pc_receive(pc_receiver *r,const uint8_t *p,uint32_t peer,bool off,uint32_t now) {
  unsigned page=p[5],len=page==PC_PAGES-1?4:30;
  if(!off || peer!=CT_PEER_BUILD || p[0]!=0x55 || p[1]!=0xaa || p[2]!=PC_WIRE ||
     p[3]!=1 || p[4]!=1 || page>=PC_PAGES || p[6]!=PC_PAGES || p[7]!=len ||
     p[38]!=1 || !uv3_crc_ok(p)) {++r->bad;return false;}
  for(unsigned i=len;i<PC_PAYLOAD;++i)if(p[8+i]){++r->bad;return false;}
  if(r->complete) {
    if(memcmp(r->data+page*PC_PAYLOAD,p+8,len)){++r->bad;return false;}
    return true;
  }
  if(r->pages&(1ULL<<page)) {
    if(memcmp(r->data+page*PC_PAYLOAD,p+8,len)) {r->pages=0;++r->bad;return false;}
    return true;
  }
  memcpy(r->data+page*PC_PAYLOAD,p+8,len);r->pages|=1ULL<<page;++r->good;
  if(r->pages==((1ULL<<PC_PAGES)-1)) {
    if(ct_u32(r->data)!=0x31435041UL || ct_u32(r->data+8)!=CT_PEER_BUILD ||
       pcw_crc(r->data)!=ct_u32(r->data+60)) {r->pages=0;++r->bad;return false;}
    r->complete=true;r->received_ms=now;
  }
  return true;
}
#endif
